"""
Message search (W19): the semantic half.

Nucleus decides WHO may see WHAT — it holds the rows and the row rules — so
this endpoint answers only "which messages read like this", as ids and scores.
Nucleus takes those ids, keeps the ones the person can see, and builds the
result from its own database. Nothing here is authorisation.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from apps.factories.context_source import ContextSourceFactory
from apps.routers.internal_key import verify_internal_key

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["search"])

SEARCH_MAX = 50


class MessageSearchRequest(BaseModel):
    company_id: str
    query: str
    top_k: int = Field(default=20, ge=1, le=SEARCH_MAX)
    # Narrow to projects the person can reach, so the search does not spend its
    # budget on rows nucleus will throw away.
    project_ids: list[str] = Field(default_factory=list)


class MessageHit(BaseModel):
    message_id: str
    score: float
    preview: str = ""


class MessageSearchResponse(BaseModel):
    hits: list[MessageHit] = Field(default_factory=list)


@router.post("/search/messages/", response_model=MessageSearchResponse)
async def search_messages(req: MessageSearchRequest, _: str = Depends(verify_internal_key)) -> MessageSearchResponse:
    query = (req.query or "").strip()
    if not query:
        return MessageSearchResponse()
    source = ContextSourceFactory.get("chat")
    collection = f"company_{req.company_id}_chat"
    filter_by = {"project_id": {"$in": req.project_ids}} if req.project_ids else None
    try:
        chunks = await source.retrieve(query=query, collection_id=collection, top_k=req.top_k, filter=filter_by)
    except Exception as exc:  # noqa: BLE001 -- a search that fails is an empty search, never a 500 in a person's face
        log.warning("[search] message search failed: %s: %s", type(exc).__name__, exc)
        return MessageSearchResponse()
    hits = []
    for chunk in chunks:
        message_id = (chunk.metadata or {}).get("message_id") or (chunk.metadata or {}).get("id")
        if not message_id:
            continue
        hits.append(MessageHit(message_id=str(message_id), score=float(chunk.score or 0.0), preview=(chunk.text or "")[:280]))
    return MessageSearchResponse(hits=hits)
