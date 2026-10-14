"""
Layer 3, item 31 — the vector store on pgvector
(docs/NEXUS-AI-REVAMP.md §1.3 Layer 3 decisions 1–8 + trial C rules; built
2026-10-13). Hash embedder: deterministic, no downloads — provider "hash" is a
real provider (embedder.py), so these are the production code paths end to end.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from ai_engine.core.specs import SearchQuery, VectorItem
from ai_engine.vector_db.store import VectorStoreBusy
from ai_engine.vector_db.txtai_store import TxtaiVectorStore

HASH = {"provider": "hash", "model_id": "hash-768"}
HASH_SMALL = {"provider": "hash", "model_id": "hash-384"}


@pytest.fixture()
def store(vector_url, tmp_path):
    s = TxtaiVectorStore(vector_url, str(tmp_path / "cfg"))
    yield s
    # an open index holds idle-in-transaction locks that would deadlock the
    # NEXT test's handle on the same schema (trial C4) — always release
    s.close()


def _item(id, text, *, kind="message", topic="t1", source=None, used=()):
    return VectorItem(id=id, kind=kind, text=text, label=f"label-{id}",
                      source=source or f"chat:{topic}", topic_id=topic,
                      used_tools=tuple(used))


def _seed(store, project="pv1", company="cv1"):
    store.index(company, project, [
        _item("m1", "the quarterly revenue grew after the pricing change", used=["github__search"]),
        _item("m2", "postgres connection pooling failed, pgbouncer fixed it", topic="t2"),
        _item("d1", "database tuning guide: indexes and pools matter",
              kind="context_source", source="src:doc9", topic=None),
    ], embedder_spec=HASH)


def test_tv1_scoped_search_and_isolation(store):
    """Item 31 — search answers only inside company+project(+topic).
    Rows for one tenant never surface for another: the same query against a
    different company id returns nothing, and a topic filter narrows chat
    memory to that topic only (item 44's SAME-TOPIC rule at the store level)."""
    _seed(store)
    store.index("cv2", "pv2", [_item("x1", "revenue pricing change talk")],
                embedder_spec=HASH)
    hits = store.search(SearchQuery(company_id="cv1", project_id="pv1",
                                    text="revenue pricing change", min_score=0.01))
    assert hits and hits[0].id == "m1"
    assert all(h.id != "x1" for h in hits)
    assert hits[0].used_tools == ("github__search",)  # decision 6 metadata
    topic_hits = store.search(SearchQuery(
        company_id="cv1", project_id="pv1", text="postgres pooling",
        topic_id="t1", kinds=("message",), min_score=0.01))
    assert all(h.id != "m2" for h in topic_hits)  # m2 lives in t2


def test_tv2_hybrid_finds_exact_term(store):
    """Item 31 — hybrid search: an exact keyword wins via pgtext.
    'pgbouncer' appears verbatim in exactly one row; hybrid (vector + keyword)
    must rank that row first even with a hash embedder (trial C3 as a test)."""
    _seed(store)
    hits = store.search(SearchQuery(company_id="cv1", project_id="pv1",
                                    text="pgbouncer", min_score=0.01))
    assert hits and hits[0].id == "m2"


def test_tv3_delete_by_source(store):
    """Item 31 — delete by source drops every chunk of one origin.
    The document's chunks share source 'src:doc9'; after delete_source they are
    gone from search while unrelated rows stay (trial C5 as a test)."""
    _seed(store)
    assert store.delete_source("cv1", "pv1", "src:doc9") == 1
    hits = store.search(SearchQuery(company_id="cv1", project_id="pv1",
                                    text="database tuning indexes", min_score=0.01))
    assert all(h.id != "d1" for h in hits)
    assert store.search(SearchQuery(company_id="cv1", project_id="pv1",
                                    text="revenue pricing", min_score=0.01))


def test_tv4_two_models_two_schemas_coexist(store):
    """Trial C4 as a regression test — different dimensions, one database.
    Two projects with different embedder dimensions (768 vs 384) get their own
    schemas; indexing the second leaves the first intact and searchable."""
    _seed(store)
    store.index("cv1", "pv-small", [_item("s1", "hello small world")],
                embedder_spec=HASH_SMALL)
    assert store.active_model("pv-small") == "hash-384"
    assert store.active_model("pv1") == "hash-768"
    assert store.search(SearchQuery(company_id="cv1", project_id="pv-small",
                                    text="hello world", min_score=0.01))
    assert store.search(SearchQuery(company_id="cv1", project_id="pv1",
                                    text="revenue pricing", min_score=0.01))


def test_tv5_fresh_process_reconnects_from_registry(store, vector_url, tmp_path):
    """Trial C6 + rule iii — a new process reconnects with NOTHING on disk.
    A second store instance with an EMPTY config dir restores the saved txtai
    config from the registry table (the truth lives in Postgres) and answers
    the same search; the transform is injected in code, never loaded."""
    _seed(store)
    store.close()  # the "old process" dies — its locks go with it
    fresh_dir = tmp_path / "other-process"
    shutil.rmtree(fresh_dir, ignore_errors=True)
    fresh = TxtaiVectorStore(vector_url, str(fresh_dir))
    try:
        hits = fresh.search(SearchQuery(company_id="cv1", project_id="pv1",
                                        text="revenue pricing change", min_score=0.01))
        assert hits and hits[0].id == "m1"
        assert (Path(fresh_dir) / fresh.active_schema("pv1")).exists()  # restored cache
    finally:
        fresh.close()


def test_tv6_reembed_builds_flips_and_drops(store):
    """Decisions 4+8 — embedder change: full rebuild, flip only when complete.
    start_reindex registers the building schema (a second start → 409's
    VectorStoreBusy); the ACTIVE index keeps answering during the build;
    run_reindex re-embeds every stored row with the new model, flips the
    registry, and drops the old schema."""
    _seed(store)
    old_schema = store.active_schema("pv1")
    store.start_reindex("cv1", "pv1", HASH_SMALL)
    with pytest.raises(VectorStoreBusy):
        store.start_reindex("cv1", "pv1", {"provider": "hash", "model_id": "hash-256"})
    assert store.reindex_status("pv1")["status"] == "building"
    # the old index still answers while the new one builds
    assert store.search(SearchQuery(company_id="cv1", project_id="pv1",
                                    text="revenue pricing", min_score=0.01))
    store.run_reindex("pv1")
    status = store.reindex_status("pv1")
    assert status["status"] == "active" and status["done"] == status["total"] == 3
    assert store.active_model("pv1") == "hash-384"
    assert store.active_schema("pv1") != old_schema
    hits = store.search(SearchQuery(company_id="cv1", project_id="pv1",
                                    text="revenue pricing change", min_score=0.01))
    assert hits and hits[0].id == "m1" and hits[0].used_tools == ("github__search",)
