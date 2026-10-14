"""
TxtaiVectorStore — the pgvector-backed implementation (Layer 3 design §3).

Trial C's rules, enforced here and nowhere else:
  (i)  one pg DATABASE, ONE SCHEMA PER INDEX — txtai indexes use fixed
       content/scoring table names, so two indexes in one schema deadlock and
       clobber each other (trial C4's hang);
  (ii) the Embeddings object is constructed fresh per process with the
       transform injected IN CODE — txtai refuses to resolve an external
       transform from saved config (ALLOW_RESOLVE_TRANSFORM guard, trial C6);
  (iii) the saved-config dir is a cache — its files are mirrored into the
       registry table, so the truth lives in Postgres and any container can
       reconnect.

The registry (public.vx_indexes) is the flip mechanism for decision 4/8: a
re-embed builds the NEW model's schema beside the old, and searches keep
answering from the ACTIVE row until the flip.

Everything here is synchronous (txtai is); callers on the event loop wrap
calls in asyncio.to_thread.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import re
import threading
from pathlib import Path
from typing import Sequence

from sqlalchemy import create_engine, text

from ai_engine.core.specs import SearchHit, SearchQuery, VectorItem
from ai_engine.vector_db.embedder import DEFAULT_EMBEDDER, Embedder, EmbedderFactory
from ai_engine.vector_db.store import VectorStore, VectorStoreBusy

log = logging.getLogger(__name__)

_REGISTRY_DDL = """
CREATE TABLE IF NOT EXISTS public.vx_indexes (
    project_id   text NOT NULL,
    schema_name  text NOT NULL,
    company_id   text NOT NULL,
    model_id     text NOT NULL,
    embedder     text NOT NULL,            -- the spec JSON (decision 3)
    status       text NOT NULL,            -- 'active' | 'building'
    config       text,                     -- saved txtai config dir, {name: b64}
    done_count   integer NOT NULL DEFAULT 0,
    total_count  integer NOT NULL DEFAULT 0,
    updated_at   timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (project_id, schema_name)
)
"""

_WALK_LIMIT = 1_000_000  # v1: a project's rows fit in memory for a re-embed
_BATCH = 64


def _slug(model_id: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", model_id.lower()).strip("_")[:20]


def _schema_for(project_id: str, model_id: str) -> str:
    return f"vx_p{re.sub(r'[^a-z0-9]+', '_', project_id.lower())}_{_slug(model_id)}"[:63]


class TxtaiVectorStore(VectorStore):
    def __init__(self, url: str, config_dir: str) -> None:
        self._url = url
        self._config_dir = Path(config_dir)
        self._engine = create_engine(url, pool_pre_ping=True)
        self._lock = threading.RLock()          # one process, serialized mutations
        self._open_indexes: dict[str, object] = {}   # schema → txtai Embeddings
        with self._engine.begin() as conn:
            conn.execute(text(_REGISTRY_DDL))

    def close(self) -> None:
        """Release every open index and pooled connection. A txtai index left
        open holds idle-in-transaction pg sessions whose locks BLOCK another
        handle opening the same schema (trial C4's deadlock) — production has
        exactly one store per process (the get_store singleton), and anything
        else, tests included, closes before another handle touches the data."""
        with self._lock:
            for emb in self._open_indexes.values():
                try:
                    emb.close()
                except Exception:  # noqa: BLE001
                    log.exception("closing an index failed")
            self._open_indexes.clear()
        self._engine.dispose()

    # ── registry ────────────────────────────────────────────────────────────

    def _row(self, project_id: str, status: str) -> dict | None:
        with self._engine.begin() as conn:
            row = conn.execute(text(
                "SELECT project_id, schema_name, company_id, model_id, embedder,"
                " status, config, done_count, total_count FROM public.vx_indexes"
                " WHERE project_id = :p AND status = :s"
            ), {"p": project_id, "s": status}).mappings().first()
        return dict(row) if row else None

    def active_model(self, project_id: str) -> str | None:
        row = self._row(project_id, "active")
        return row["model_id"] if row else None

    def has_index(self, project_id: str) -> bool:
        return self._row(project_id, "active") is not None

    def active_schema(self, project_id: str) -> str | None:
        row = self._row(project_id, "active")
        return row["schema_name"] if row else None

    def projects_for_company(self, company_id: str) -> list[str]:
        with self._engine.begin() as conn:
            rows = conn.execute(text(
                "SELECT project_id FROM public.vx_indexes"
                " WHERE company_id = :c AND status = 'active'"
            ), {"c": company_id}).fetchall()
        return [r[0] for r in rows]

    # ── open / create ───────────────────────────────────────────────────────

    def _txtai_config(self, schema: str, embedder: Embedder) -> dict:
        # a plain FUNCTION, not a bound method — txtai treats any non-function
        # callable as a factory and calls it with no arguments
        def transform(texts, _embedder=embedder):
            return _embedder.embed(texts)

        return {
            "method": "external", "transform": transform,
            "backend": "pgvector",
            "pgvector": {"url": self._url, "table": "vectors", "schema": schema},
            "content": self._url,
            # schema must be INSIDE the scoring dict too: PGText reads its own
            # config only — a top-level schema never reaches it, and all
            # indexes would then share (and clobber) one scoring table in
            # public, deadlocking on each other's open sessions.
            "scoring": {"method": "pgtext", "url": self._url, "schema": schema},
            "schema": schema, "hybrid": True,
        }

    def _cfg_dir(self, schema: str) -> Path:
        return self._config_dir / schema

    def _persist(self, schema: str, emb) -> None:
        """save(dir), then mirror the dir into the registry (rule iii)."""
        directory = self._cfg_dir(schema)
        directory.mkdir(parents=True, exist_ok=True)
        emb.save(str(directory))
        files = {
            name: base64.b64encode((directory / name).read_bytes()).decode()
            for name in os.listdir(directory)
            if (directory / name).is_file()
        }
        with self._engine.begin() as conn:
            conn.execute(text(
                "UPDATE public.vx_indexes SET config = :c, updated_at = now()"
                " WHERE schema_name = :s"
            ), {"c": json.dumps(files), "s": schema})

    def _restore_cfg_dir(self, schema: str, config_json: str | None) -> bool:
        directory = self._cfg_dir(schema)
        if (directory / "config").exists() or (directory / "config.json").exists():
            return True
        if not config_json:
            return False
        directory.mkdir(parents=True, exist_ok=True)
        for name, b64 in json.loads(config_json).items():
            (directory / name).write_bytes(base64.b64decode(b64))
        return True

    def _embedder_for_row(self, row: dict) -> Embedder:
        try:
            return EmbedderFactory.build(json.loads(row["embedder"]))
        except Exception:  # noqa: BLE001 — an unreadable spec falls back by model id
            return EmbedderFactory.for_model(row["model_id"])

    def _open(self, row: dict):
        """The ACTIVE index as a live txtai Embeddings (process-cached).
        Reconnect = restored config dir + transform injected in code (C6)."""
        schema = row["schema_name"]
        with self._lock:
            if schema in self._open_indexes:
                return self._open_indexes[schema]
            from txtai import Embeddings  # lazy: pulls torch
            embedder = self._embedder_for_row(row)
            config = self._txtai_config(schema, embedder)
            emb = Embeddings()
            if self._restore_cfg_dir(schema, row.get("config")):
                emb.load(str(self._cfg_dir(schema)), config=config)
            else:
                # a brand-new index: nothing saved yet, first upsert creates it
                emb = Embeddings(config)
            self._open_indexes[schema] = emb
            return emb

    def _create(self, company_id: str, project_id: str,
                embedder_spec: dict | None, status: str = "active") -> dict:
        spec = embedder_spec or DEFAULT_EMBEDDER
        embedder = EmbedderFactory.build(spec)
        schema = _schema_for(project_id, embedder.model_id())
        with self._engine.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
            conn.execute(text(
                "INSERT INTO public.vx_indexes"
                " (project_id, schema_name, company_id, model_id, embedder, status)"
                " VALUES (:p, :s, :c, :m, :e, :st)"
                " ON CONFLICT (project_id, schema_name) DO NOTHING"
            ), {"p": project_id, "s": schema, "c": company_id,
                "m": embedder.model_id(), "e": json.dumps(spec), "st": status})
        return self._row(project_id, status)

    # ── VectorStore ─────────────────────────────────────────────────────────

    @staticmethod
    def _data(item: VectorItem, company_id: str, project_id: str) -> dict:
        return {
            "text": item.text, "company": company_id, "project": project_id,
            "topic": item.topic_id or "", "kind": item.kind, "label": item.label,
            "source": item.source, "used_tools": json.dumps(list(item.used_tools)),
            "created_at": item.created_at or "",
        }

    def index(self, company_id: str, project_id: str,
              items: Sequence[VectorItem],
              embedder_spec: dict | None = None) -> str:
        with self._lock:
            row = self._row(project_id, "active") or self._create(
                company_id, project_id, embedder_spec)
            emb = self._open(row)
            emb.upsert([(i.id, self._data(i, company_id, project_id), None)
                        for i in items])
            self._persist(row["schema_name"], emb)
            return row["model_id"]

    def search(self, query: SearchQuery) -> list[SearchHit]:
        row = self._row(query.project_id, "active")
        if row is None:
            return []
        emb = self._open(row)
        where = ["similar(:q)", "company = :c", "project = :p"]
        parameters = {"q": query.text, "c": query.company_id, "p": query.project_id}
        if query.topic_id is not None:
            where.append("topic = :t")
            parameters["t"] = query.topic_id
        if query.kinds:
            ors = " or ".join(f"kind = :k{n}" for n in range(len(query.kinds)))
            where.append(f"({ors})")
            parameters.update({f"k{n}": k for n, k in enumerate(query.kinds)})
        sql = ("select id, text, score, kind, label, topic, used_tools, created_at from txtai"
               " where " + " and ".join(where))
        results = emb.search(sql, query.top_k, parameters=parameters)
        hits = []
        for r in results:
            score = float(r.get("score") or 0.0)
            if score < query.min_score:
                continue
            try:
                used = tuple(json.loads(r.get("used_tools") or "[]"))
            except Exception:  # noqa: BLE001
                used = ()
            hits.append(SearchHit(
                id=str(r["id"]), kind=r.get("kind") or "", label=r.get("label") or "",
                score=score, text=r.get("text") or "",
                topic_id=(r.get("topic") or None), used_tools=used,
                created_at=r.get("created_at") or "",
            ))
        return hits

    def _ids_where(self, row: dict, clause: str, parameters: dict) -> list[str]:
        emb = self._open(row)
        rows = emb.search(f"select id from txtai where {clause}", _WALK_LIMIT,
                          parameters=parameters)
        return [str(r["id"]) for r in rows]

    def delete_source(self, company_id: str, project_id: str, source: str) -> int:
        """company_id="" skips the company filter — the legacy context-source
        delete carries only the collection key, and the per-project schema is
        already single-tenant (a project belongs to one company)."""
        with self._lock:
            row = self._row(project_id, "active")
            if row is None:
                return 0
            clause = "source = :s" + (" and company = :c" if company_id else "")
            parameters = {"s": source}
            if company_id:
                parameters["c"] = company_id
            ids = self._ids_where(row, clause, parameters)
            if not ids:
                return 0
            emb = self._open(row)
            deleted = emb.delete(ids)
            self._persist(row["schema_name"], emb)
            return len(deleted or [])

    def delete_ids(self, company_id: str, project_id: str,
                   ids: Sequence[str]) -> int:
        with self._lock:
            row = self._row(project_id, "active")
            if row is None or not ids:
                return 0
            emb = self._open(row)
            deleted = emb.delete(list(ids))
            self._persist(row["schema_name"], emb)
            return len(deleted or [])

    # ── re-embed (decisions 4 + 8) ──────────────────────────────────────────

    def start_reindex(self, company_id: str, project_id: str,
                      embedder_spec: dict) -> dict:
        """Create the BUILDING row (and its schema) or refuse when one exists.
        The walk itself is run_reindex — the router calls it in the background."""
        with self._lock:
            if self._row(project_id, "building") is not None:
                raise VectorStoreBusy(f"a reindex is already building for {project_id}")
            new_row = self._create(company_id, project_id, embedder_spec,
                                   status="building")
            if new_row is None:
                # same model as the active index — the schema collides; treat
                # as busy-equivalent misuse rather than silently rebuilding
                raise VectorStoreBusy("the new embedder matches the active index")
            return new_row

    def run_reindex(self, project_id: str) -> None:
        """Walk the OLD schema's stored raw text into the NEW one, then flip.
        Search keeps answering from the ACTIVE row the whole time."""
        new_row = self._row(project_id, "building")
        if new_row is None:
            return
        old_row = self._row(project_id, "active")
        embedder_spec = json.loads(new_row["embedder"])
        rows: list[dict] = []
        if old_row is not None:
            old = self._open(old_row)
            rows = old.search(
                "select id, text, kind, label, source, topic, used_tools,"
                " created_at, company, project from txtai", _WALK_LIMIT)
        with self._engine.begin() as conn:
            conn.execute(text(
                "UPDATE public.vx_indexes SET total_count = :t, updated_at = now()"
                " WHERE project_id = :p AND status = 'building'"
            ), {"t": len(rows), "p": project_id})
        items = [
            VectorItem(
                id=str(r["id"]), kind=r.get("kind") or "", text=r.get("text") or "",
                label=r.get("label") or "", source=r.get("source") or "",
                topic_id=(r.get("topic") or None),
                used_tools=tuple(json.loads(r.get("used_tools") or "[]")),
                created_at=r.get("created_at") or "",
            ) for r in rows
        ]
        done = 0
        for start in range(0, len(items), _BATCH) if items else []:
            batch = items[start:start + _BATCH]
            with self._lock:
                emb = self._open(new_row)
                emb.upsert([(i.id, self._data(i, new_row["company_id"], project_id), None)
                            for i in batch])
            done += len(batch)
            with self._engine.begin() as conn:
                conn.execute(text(
                    "UPDATE public.vx_indexes SET done_count = :d, updated_at = now()"
                    " WHERE project_id = :p AND status = 'building'"
                ), {"d": done, "p": project_id})
        with self._lock:
            emb = self._open(new_row)
            if not items:
                # an empty project still needs a materialized, reconnectable index
                emb.upsert([("__init__", self._data(VectorItem(
                    id="__init__", kind="recall", text="init", label="init",
                    source="__init__"), new_row["company_id"], project_id), None)])
                emb.delete(["__init__"])
            self._persist(new_row["schema_name"], emb)
            # the flip (decision 8). The old index's handle closes FIRST:
            # DROP SCHEMA needs exclusive locks, and an open txtai index holds
            # idle-in-transaction sessions that would block the drop forever.
            if old_row is not None:
                stale = self._open_indexes.pop(old_row["schema_name"], None)
                if stale is not None:
                    try:
                        stale.close()
                    except Exception:  # noqa: BLE001
                        log.exception("closing the retired index failed")
            with self._engine.begin() as conn:
                if old_row is not None:
                    conn.execute(text(
                        "DELETE FROM public.vx_indexes WHERE project_id = :p"
                        " AND schema_name = :s"
                    ), {"p": project_id, "s": old_row["schema_name"]})
                    conn.execute(text(
                        f'DROP SCHEMA IF EXISTS "{old_row["schema_name"]}" CASCADE'))
                conn.execute(text(
                    "UPDATE public.vx_indexes SET status = 'active', updated_at = now()"
                    " WHERE project_id = :p AND status = 'building'"
                ), {"p": project_id})

    def reindex_status(self, project_id: str) -> dict:
        building = self._row(project_id, "building")
        if building is not None:
            return {"status": "building", "done": building["done_count"],
                    "total": building["total_count"]}
        active = self._row(project_id, "active")
        if active is not None:
            return {"status": "active", "done": active["done_count"],
                    "total": active["total_count"]}
        return {"status": "none", "done": 0, "total": 0}
