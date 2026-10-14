"""
Layer 3, items 24/44 + recall — the embed endpoints, legacy contracts kept
(docs/NEXUS-AI-REVAMP.md §1.3 "Legacy contract verification" + decisions 5/6/8/11;
built 2026-10-13). Shapes are 0.8.0's (NA/routers/embed.py), additions are the
settled ones only: `embedder`, `used_tools`, the reindex pair, code refused.
"""
from __future__ import annotations

import os
import time

import httpx
import pytest

from conftest import INTERNAL_KEY
from ai_engine.core.specs import SearchQuery
from ai_engine.vector_db.txtai_store import TxtaiVectorStore

pytestmark = pytest.mark.asyncio

HASH = {"provider": "hash", "model_id": "hash-768"}


@pytest.fixture()
def read_store(vector_url, servers) -> TxtaiVectorStore:
    """THE APP'S OWN singleton (the servers run in-process) — a second handle
    on the same schemas would deadlock on the open one's idle-in-transaction
    locks (trial C4), and production has exactly one store per process."""
    from fastapi_app.routers.embed import get_store
    return get_store()


async def _post(harness, path, payload, key=INTERNAL_KEY):
    async with httpx.AsyncClient(timeout=60.0) as client:
        return await client.post(f"{harness.app_url}{path}", json=payload,
                                 headers={"X-Internal-Key": key} if key else {})


async def _delete(harness, path):
    async with httpx.AsyncClient(timeout=60.0) as client:
        return await client.delete(f"{harness.app_url}{path}",
                                   headers={"X-Internal-Key": INTERNAL_KEY})


def _doc_payload(**overrides):
    base = {
        "source_id": "srcA", "type": "file", "label": "guide.md",
        "content": "Alpha paragraph about postgres tuning.\n\n" * 40,
        "topic_id": "te-t1", "channel_id": "ch1",
        "project_id": "pe1", "company_id": "ce1", "embedder": HASH,
    }
    base.update(overrides)
    return base


async def test_te1_document_embed_chunks_and_keys(harness, vector_url, read_store):
    """Item 24 — POST /embed/ chunks a document and answers the 0.8.0 shape.
    A long file becomes several chunks; the response carries source_id,
    chunks_count and collection_id='{project_id}:{source_id}' (design Open d),
    and the rows are searchable, scoped to the project."""
    response = await _post(harness, "/api/v1/embed/", _doc_payload())
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["source_id"] == "srcA"
    assert body["collection_id"] == "pe1:srcA"
    assert body["chunks_count"] > 1
    hits = read_store.search(SearchQuery(company_id="ce1", project_id="pe1",
                                         text="postgres tuning", min_score=0.01))
    assert hits and hits[0].kind == "context_source"


async def test_te2_code_is_refused(harness, vector_url):
    """Decision 5/11 — type='code' is refused with a clear 422.
    Code files ride the prompt; they are never embedded. The error text points
    at the decision so nucleus-side callers know it is deliberate."""
    response = await _post(harness, "/api/v1/embed/", _doc_payload(type="code"))
    assert response.status_code == 422
    assert "code" in response.json()["detail"]


async def test_te3_context_source_delete(harness, vector_url, read_store):
    """Item 24 — DELETE /embed/context-source/{collection_id}/ empties the source.
    The collection key alone (0.8.0 contract — no other scope travels) finds
    and drops every chunk; unrelated rows survive."""
    await _post(harness, "/api/v1/embed/", _doc_payload())
    await _post(harness, "/api/v1/embed/", _doc_payload(
        source_id="srcKeep", label="keep.md", content="Keep me around, carrots."))
    response = await _delete(harness, "/api/v1/embed/context-source/pe1:srcA/")
    assert response.status_code == 200 and response.json() == {"ok": True}
    remaining = read_store.search(SearchQuery(
        company_id="ce1", project_id="pe1", text="postgres tuning",
        kinds=("context_source",), min_score=0.01))
    assert all("srcA" not in h.id for h in remaining)
    assert read_store.search(SearchQuery(company_id="ce1", project_id="pe1",
                                         text="carrots", min_score=0.01))


async def test_te4_message_embed_and_delete(harness, vector_url, read_store):
    """Item 44 — a chat message embeds with used_tools and deletes by id.
    The response is 0.8.0's MessageEmbedResponse (collection + embedding_model);
    used_tools comes back as search metadata (decision 6); the M6 delete drops
    that row AND the message's tool memory (item 27 decision 8: rows with
    source='toolres:{message_id}' die with the message), found by company scan
    (no project_id sent — 0.8.0 shape)."""
    payload = {
        "message_id": "me-m1", "company_id": "ce1", "sequence": 4,
        "topic_id": "te-t1", "channel_id": "ch1", "project_id": "pe1",
        "sender_id": "u1", "sender_name": "Noaman", "sender_type": "human",
        "content": "we chose pgbouncer for pooling", "created_at": "2026-10-13T00:00:00Z",
        "used_tools": ["github__search"], "embedder": HASH,
    }
    response = await _post(harness, "/api/v1/embed/message/", payload)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ok"] is True and body["embedding_model"] == "hash-768"
    assert body["collection"].startswith("vx_p")
    hits = read_store.search(SearchQuery(company_id="ce1", project_id="pe1",
                                         text="pgbouncer pooling", min_score=0.01))
    assert hits and hits[0].id == "me-m1" and hits[0].used_tools == ("github__search",)
    # item 27 decision 8: the reply's tool memory hangs off the message by source
    from ai_engine.core.specs import VectorItem
    read_store.index("ce1", "pe1", [VectorItem(
        id="me-m1:tr0", kind="tool_result", text="remote csv figures worth keeping",
        label="read_file sales.csv", source="toolres:me-m1", topic_id="te-t1")])
    response = await _delete(harness, "/api/v1/embed/message/me-m1/?company_id=ce1")
    assert response.json() == {"ok": True}
    hits = read_store.search(SearchQuery(company_id="ce1", project_id="pe1",
                                         text="pgbouncer pooling",
                                         kinds=("message",), min_score=0.01))
    assert all(h.id != "me-m1" for h in hits)
    hits = read_store.search(SearchQuery(company_id="ce1", project_id="pe1",
                                         text="remote csv figures",
                                         kinds=("tool_result",), min_score=0.01))
    assert all(not h.id.startswith("me-m1:") for h in hits)  # memory died with it


async def test_te5_recall_upserts_and_deletes(harness, vector_url, read_store):
    """W5 (decision 11) — a recall entry upserts on the same id and deletes.
    Embedding the same entry_id twice leaves ONE row carrying the second text
    (an edit replaces, 0.8.0's documented behaviour); the delete drops it."""
    payload = {
        "entry_id": "re-1", "company_id": "ce1", "project_id": "pe1",
        "kind": "decision", "text": "we deploy on fridays", "author_name": "Noaman",
        "embedder": HASH,
    }
    assert (await _post(harness, "/api/v1/embed/recall/", payload)).status_code == 200
    payload["text"] = "we never deploy on fridays"
    response = await _post(harness, "/api/v1/embed/recall/", payload)
    assert response.json()["ok"] is True
    hits = read_store.search(SearchQuery(company_id="ce1", project_id="pe1",
                                         text="deploy fridays",
                                         kinds=("recall",), min_score=0.01))
    assert [h.id for h in hits] == ["re-1"]
    assert "never" in hits[0].text
    await _delete(harness, "/api/v1/embed/recall/re-1/?company_id=ce1")
    hits = read_store.search(SearchQuery(company_id="ce1", project_id="pe1",
                                         text="deploy fridays",
                                         kinds=("recall",), min_score=0.01))
    assert all(h.id != "re-1" for h in hits)


async def test_te6_auth_and_unconfigured(harness, vector_url):
    """Locks — every embed endpoint needs the internal key; no URL = 503.
    A request without X-Internal-Key is 401 (same second lock as /trigger);
    with NEXUS_VECTOR_DB_URL cleared the endpoints answer 503 'not configured'
    instead of crashing — the feature-off state is a real production state."""
    response = await _post(harness, "/api/v1/embed/", _doc_payload(), key=None)
    assert response.status_code == 401
    saved = os.environ.get("NEXUS_VECTOR_DB_URL", "")
    os.environ["NEXUS_VECTOR_DB_URL"] = ""
    try:
        response = await _post(harness, "/api/v1/embed/", _doc_payload())
        assert response.status_code == 503
    finally:
        os.environ["NEXUS_VECTOR_DB_URL"] = saved


async def test_te7_reindex_flips_and_refuses_doubles(harness, vector_url, read_store):
    """Decisions 4+8 — POST /embed/reindex/ rebuilds in the background.
    202 is immediate; polling the status endpoint reaches status=active with
    the NEW model; rows survive re-embedded; a reindex started while one is
    building answers 409."""
    await _post(harness, "/api/v1/embed/", _doc_payload(
        source_id="srcR", content="reindex survivors live here"))
    read_store.start_reindex("ce1", "pe1", {"provider": "hash", "model_id": "hash-256"})
    response = await _post(harness, "/api/v1/embed/reindex/", {
        "company_id": "ce1", "project_id": "pe1",
        "embedder": {"provider": "hash", "model_id": "hash-128"},
    })
    assert response.status_code == 409  # one at a time
    read_store.run_reindex("pe1")  # finish the direct one
    response = await _post(harness, "/api/v1/embed/reindex/", {
        "company_id": "ce1", "project_id": "pe1",
        "embedder": {"provider": "hash", "model_id": "hash-128"},
    })
    assert response.status_code == 202, response.text
    async with httpx.AsyncClient(timeout=30.0) as client:
        for _ in range(100):
            status = (await client.get(
                f"{harness.app_url}/api/v1/embed/reindex/pe1/status/",
                headers={"X-Internal-Key": INTERNAL_KEY})).json()
            if status["status"] == "active" and read_store.active_model("pe1") == "hash-128":
                break
            time.sleep(0.1)
    assert read_store.active_model("pe1") == "hash-128"
    hits = read_store.search(SearchQuery(company_id="ce1", project_id="pe1",
                                         text="reindex survivors", min_score=0.01))
    assert hits
