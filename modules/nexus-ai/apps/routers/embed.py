"""
Embedding endpoints — nexus-nucleus → nexus-ai.

Routers are thin — they only verify auth and delegate to the right
ContextSource plugin via ContextSourceFactory. No business logic here.

POST /api/v1/embed/          → DocumentContextSource.ingest()
POST /api/v1/embed/message/  → ChatContextSource.ingest()
"""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security.api_key import APIKeyHeader

from apps.core.config import settings
from apps.schemas.embed import EmbedRequest, EmbedResponse, MessageEmbedRequest, MessageEmbedResponse
from apps.factories.context_source import ContextSourceFactory

router = APIRouter(prefix="/api/v1", tags=["embed"])

_api_key_header = APIKeyHeader(name="X-Internal-Key", auto_error=False)


def _verify_key(key: str = Depends(_api_key_header)):
    if key != settings.INTERNAL_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid internal API key")
    return key


@router.post("/embed/", response_model=EmbedResponse)
async def embed(
    req: EmbedRequest,
    _: str = Depends(_verify_key),
) -> EmbedResponse:
    """Chunk, embed, and store a document or code context source."""
    return await ContextSourceFactory.get(req.type).ingest(req)


@router.post("/embed/message/", response_model=MessageEmbedResponse)
async def embed_message(
    req: MessageEmbedRequest,
    _: str = Depends(_verify_key),
) -> MessageEmbedResponse:
    """Embed a chat message into the company chat collection."""
    return await ContextSourceFactory.get("chat").ingest(req)
