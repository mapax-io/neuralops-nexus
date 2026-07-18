"""
POST /api/v1/embed/
Called by nexus-nucleus when a context source is attached to a topic.
Chunks, embeds, stores in Chroma. Returns collection_id.
"""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security.api_key import APIKeyHeader

from apps.core.config import settings
from apps.schemas.embed import EmbedRequest, EmbedResponse
from apps.managers.embedding_manager import EmbeddingManager
from apps.factories.embedding import EmbeddingFactory
from apps.factories.vectorstore import VectorStoreFactory

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
    """
    Chunk + embed a context source and store in Chroma.
    Returns collection_id for nexus-nucleus to save back to ContextSource.
    """
    manager = EmbeddingManager(
        embedder=EmbeddingFactory.get(),
        store=VectorStoreFactory.get(),
    )
    return await manager.ingest(req)
