"""
Step 6 (docs/NUCLEUS-REVAMP.md) — the message-search endpoint.

POST /api/v1/search/messages/ — the exact contract nucleus's chat/search.py
has been calling since 0.8.0 (it was a LEGACY engine endpoint; the rebuilt
module never had it, so semantic chat search would have silently degraded to
literal matching at switch-over). It also serves the gateway's search_memory
tool. {company_id, query, top_k, project_ids} → {"hits": [{"message_id",
"score"}]}.

Authorisation is NUCLEUS's job — it filters the returned ids by what the
caller may see before anything reaches a person. This endpoint only ranks.
Internal-key gated like every other endpoint here.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ai_engine.core.specs import SearchQuery
from fastapi_app.routers.embed import get_store
from fastapi_app.routers.trigger import _verify_key

router = APIRouter(prefix="/api/v1", tags=["search"])

MAX_TOP_K = 50


class MessageSearchRequest(BaseModel):
    company_id: str
    query: str
    top_k: int = 20
    project_ids: list[str] = Field(default_factory=list)


class MessageHit(BaseModel):
    message_id: str
    score: float


class MessageSearchResponse(BaseModel):
    hits: list[MessageHit]


@router.post("/search/messages/", response_model=MessageSearchResponse)
def search_messages(req: MessageSearchRequest, _: str = Depends(_verify_key)) -> MessageSearchResponse:
    """Rank chat messages across the given projects, best first. Empty hits
    when nothing matches or no project has an index yet; 503 when the vector
    store is off (NEXUS_VECTOR_DB_URL unset) — nucleus's caller falls back to
    its literal search either way."""
    store = get_store()
    top_k = max(1, min(req.top_k, MAX_TOP_K))
    hits: list[MessageHit] = []
    for project_id in req.project_ids:
        for hit in store.search(SearchQuery(
            company_id=req.company_id,
            project_id=project_id,
            text=req.query,
            kinds=("message",),
            top_k=top_k,
        )):
            hits.append(MessageHit(message_id=hit.id, score=hit.score))
    hits.sort(key=lambda h: h.score, reverse=True)
    return MessageSearchResponse(hits=hits[:top_k])
