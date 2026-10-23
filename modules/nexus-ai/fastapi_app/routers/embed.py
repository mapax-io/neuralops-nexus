"""
The embed endpoints (Layer 3, items 24/44) — nucleus → nexus-ai.
(The Recall embed pair left with the Recall feature, owner's ruling 2026-10-22.)

Paths and shapes ported from 0.8.0 (verified in docs/NEXUS-AI-REVAMP.md's
"Legacy contract verification" block — NA/routers/embed.py + schemas/embed.py),
with the settled additions: optional `embedder` on ingestion (the project's
setting; omitted = system default — decision 3), optional `used_tools` on
message embeds (decision 6), `type="code"` refused (decision 5/11), and the
NEW reindex pair (decision 8). `GET /directives/` is deliberately NOT ported
(decision 11 — handoff asks nucleus to confirm it is unused).

Handlers are sync `def` on purpose: FastAPI runs them in the threadpool, which
is where txtai's blocking work belongs. 503 = the feature is off
(NEXUS_VECTOR_DB_URL unset).
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field

from ai_engine.core.specs import VectorItem
from ai_engine.vector_db.chunking import chunk_text
from ai_engine.vector_db.reembed import ReembedJob
from ai_engine.vector_db.store import VectorStoreBusy
from ai_engine.vector_db.txtai_store import TxtaiVectorStore
from fastapi_app.routers.trigger import _verify_key

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["embed"])

def get_store() -> TxtaiVectorStore:
    """The engine's one store (ai_engine.vector_db.get_store) — importing
    txtai (→ torch) is paid on first use only. Not configured → 503."""
    from ai_engine.vector_db import get_store as engine_store
    store = engine_store()
    if store is None:
        raise HTTPException(status_code=503, detail="vector store is not configured (NEXUS_VECTOR_DB_URL)")
    return store


# ── contracts (0.8.0 shapes + settled additions) ────────────────────────────

class EmbedRequest(BaseModel):
    source_id: str
    type: str                        # "file" ("code" is refused — decision 5)
    label: str
    content: str
    language: str | None = None      # accepted for contract parity, unused
    topic_id: str | None = None
    channel_id: str | None = None
    project_id: str | None = None
    company_id: str | None = None
    embedder: dict | None = None     # the project's setting; None = default


class EmbedResponse(BaseModel):
    source_id: str
    collection_id: str               # "{project_id}:{source_id}" — design Open (d)
    chunks_count: int


class MessageEmbedRequest(BaseModel):
    message_id: str
    company_id: str
    sequence: int
    topic_id: str
    channel_id: str
    project_id: str
    sender_id: str
    sender_name: str
    sender_type: str                 # "human" | "persona"
    content: str
    created_at: str
    used_tools: list[str] = Field(default_factory=list)  # decision 6
    embedder: dict | None = None


class MessageEmbedResponse(BaseModel):
    message_id: str
    collection: str
    embedding_model: str
    ok: bool


class ReindexRequest(BaseModel):
    company_id: str
    project_id: str
    embedder: dict                   # the NEW spec — the whole point of the job


# ── ingestion (items 24 / 44) ──────────────────────────────────────

@router.post("/embed/", response_model=EmbedResponse)
def embed(req: EmbedRequest, _: str = Depends(_verify_key)) -> EmbedResponse:
    """Chunk, embed and store a document context source."""
    if req.type == "code":
        # decision 5: code is NEVER embedded — the code-graph MCP (item 32)
        # inspects code; nucleus stops sending this (handoff).
        raise HTTPException(status_code=422, detail="type='code' is not embedded any more (NEXUS-AI-REVAMP §1.3 Layer 3 decision 5); attach code with the prompt or use the code-graph MCP")
    if req.type != "file":
        raise HTTPException(status_code=422, detail=f"unknown context source type {req.type!r}")
    if not req.project_id or not req.company_id:
        raise HTTPException(status_code=422, detail="project_id and company_id are required")
    chunks = chunk_text(req.content)
    items = [
        VectorItem(
            id=f"{req.source_id}:{n}", kind="context_source", text=chunk,
            label=req.label, source=f"src:{req.source_id}", topic_id=req.topic_id,
        ) for n, chunk in enumerate(chunks)
    ]
    store = get_store()
    store.index(req.company_id, req.project_id, items, embedder_spec=req.embedder)
    return EmbedResponse(
        source_id=req.source_id,
        collection_id=f"{req.project_id}:{req.source_id}",
        chunks_count=len(items),
    )


@router.delete("/embed/context-source/{collection_id}/")
def delete_context_source(collection_id: str, _: str = Depends(_verify_key)) -> dict:
    """Drop every chunk of one context source. collection_id is what POST
    /embed/ answered: "{project_id}:{source_id}" (it is the only scope the
    0.8.0 contract carries — design Open (d))."""
    project_id, _, source_id = collection_id.partition(":")
    if not source_id:
        raise HTTPException(status_code=422, detail="collection_id must be '{project_id}:{source_id}'")
    get_store().delete_source("", project_id, f"src:{source_id}")
    return {"ok": True}


@router.post("/embed/message/", response_model=MessageEmbedResponse)
def embed_message(req: MessageEmbedRequest, _: str = Depends(_verify_key)) -> MessageEmbedResponse:
    """Embed one chat message into the project index (item 44: topic-scoped at
    SEARCH time; used_tools rides as metadata)."""
    store = get_store()
    item = VectorItem(
        id=req.message_id, kind="message", text=req.content,
        label=f"{req.sender_name} ({req.sender_type})",
        source=f"chat:{req.topic_id}", topic_id=req.topic_id,
        used_tools=tuple(req.used_tools),
    )
    model_id = store.index(req.company_id, req.project_id, [item],
                           embedder_spec=req.embedder)
    return MessageEmbedResponse(
        message_id=req.message_id,
        collection=store.active_schema(req.project_id) or "",
        embedding_model=model_id, ok=True,
    )


@router.delete("/embed/message/{message_id}/")
def delete_message_vector(message_id: str, company_id: str,
                          project_id: str | None = None,
                          _: str = Depends(_verify_key)) -> dict:
    """Drop one message's vector (M6: excluded from context) AND its tool
    memory (item 27 decision 8: rows saved from the reply's tool outputs carry
    source="toolres:{message_id}" — a message delete drops its memory with it).
    The 0.8.0 contract carries only company_id, so without project_id the
    company's active indexes are scanned — pass project_id to skip the scan."""
    store = get_store()
    projects = [project_id] if project_id else store.projects_for_company(company_id)
    for project in projects:
        dropped = store.delete_ids(company_id, project, [message_id])
        dropped += store.delete_source(company_id, project, f"toolres:{message_id}")
        if dropped:
            break
    return {"ok": True}


# REMOVED (owner's ruling 2026-10-22): POST /embed/recall/ + DELETE
# /embed/recall/{entry_id}/ — the Recall feature (W5) left the product.


# ── reindex (decisions 4 + 8) ───────────────────────────────────────────────

@router.post("/embed/reindex/", status_code=202)
def start_reindex(req: ReindexRequest, background: BackgroundTasks,
                  _: str = Depends(_verify_key)) -> dict:
    """Embedder changed → rebuild EVERYTHING for the project (decision 4).
    202 + background walk; nucleus locks the project and polls status. A
    build already running → 409."""
    job = ReembedJob(get_store())
    try:
        job.start(req.company_id, req.project_id, req.embedder)
    except VectorStoreBusy as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    background.add_task(job.run, req.project_id)
    return {"ok": True, "status": "building"}


@router.get("/embed/reindex/{project_id}/status/")
def reindex_status(project_id: str, _: str = Depends(_verify_key)) -> dict:
    return ReembedJob(get_store()).status(project_id)
