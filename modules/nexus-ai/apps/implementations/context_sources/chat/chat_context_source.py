"""
ChatContextSource — plugin entry point for chat message context.

Implements the ContextSource interface.
The system talks only to this class — internals are private to this module.
"""
from __future__ import annotations

from apps.interfaces.context_source import ContextSource
from apps.interfaces.embedding import EmbeddingModel
from apps.interfaces.vectorstore import VectorStore, Chunk
from apps.schemas.embed import MessageEmbedRequest, MessageEmbedResponse

from .chat_embedding_manager import ChatEmbeddingManager
from .chat_context_manager import ChatContextManager


class ChatContextSource(ContextSource):
    def __init__(self, embedder: EmbeddingModel, store: VectorStore) -> None:
        self._ingestor = ChatEmbeddingManager(embedder=embedder, store=store)
        self._retriever = ChatContextManager(embedder=embedder, store=store)
        self._store = store

    async def ingest(self, req: MessageEmbedRequest) -> MessageEmbedResponse:
        """Embed and store a chat message."""
        return await self._ingestor.ingest(req)

    async def retrieve(
        self,
        query: str,
        collection_id: str,
        top_k: int = 10,
        filter: dict | None = None,
    ) -> list[Chunk]:
        """Search past chat messages for semantic matches."""
        return await self._retriever.retrieve(
            query=query,
            collection_id=collection_id,
            top_k=top_k,
            filter=filter,
        )

    async def delete(self, collection_id: str) -> None:
        """Remove all chat vectors for a company (used during teardown)."""
        await self._store.delete_collection(collection_id)
