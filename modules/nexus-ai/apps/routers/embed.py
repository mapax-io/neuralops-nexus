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


@router.get("/directives/")
async def list_directives(_: str = Depends(_verify_key)) -> list[dict]:
    """Return all registered context directives with help text."""
    return ContextSourceFactory.get_all_directives()


@router.post("/embed/", response_model=EmbedResponse)
async def embed(
    req: EmbedRequest,
    _: str = Depends(_verify_key),
) -> EmbedResponse:
    """Chunk, embed, and store a document or code context source."""
    return await ContextSourceFactory.get(req.type).ingest(req)


@router.delete("/embed/context-source/{collection_id}/")
async def delete_context_source(
    collection_id: str,
    _: str = Depends(_verify_key),
) -> dict:
    """Delete all vectors for a context source collection from ChromaDB."""
    await ContextSourceFactory.get("file").delete(collection_id)
    return {"ok": True}


@router.delete("/embed/message/{message_id}/")
async def delete_message_vector(
    message_id: str,
    company_id: str,
    _: str = Depends(_verify_key),
) -> dict:
    """
    Delete a single chat message vector from ChromaDB.
    Called by nexus-nucleus when a message is excluded from context (M6).
    """
    from apps.implementations.context_sources.chat.chat_context_source import ChatContextSource
    from apps.factories.embedding import EmbeddingFactory
    from apps.factories.vectorstore import VectorStoreFactory
    chat_source = ChatContextSource(
        embedder=EmbeddingFactory.get(),
        store=VectorStoreFactory.get(),
    )
    await chat_source.delete_message(message_id, company_id)
    return {"ok": True}


@router.post("/embed/message/", response_model=MessageEmbedResponse)
async def embed_message(
    req: MessageEmbedRequest,
    _: str = Depends(_verify_key),
) -> MessageEmbedResponse:
    """Embed a chat message into the company chat collection."""
    return await ContextSourceFactory.get("chat").ingest(req)
