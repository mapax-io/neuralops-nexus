"""
DocumentContextSource — plugin entry point for document/code context.

Implements the ContextSource interface.
The system talks only to this class — internals are private to this module.
"""
from __future__ import annotations

from apps.interfaces.context_source import ContextSource
from apps.interfaces.embedding import EmbeddingModel
from apps.interfaces.vectorstore import VectorStore, Chunk
from apps.schemas.embed import EmbedRequest, EmbedResponse

from .document_embedding_manager import DocumentEmbeddingManager
from .document_context_manager import DocumentContextManager


class DocumentContextSource(ContextSource):
    directive = "file"
    help = "Search an attached file — @file report.pdf"

    def __init__(self, embedder: EmbeddingModel, store: VectorStore) -> None:
        self._ingestor = DocumentEmbeddingManager(embedder=embedder, store=store)
        self._retriever = DocumentContextManager(embedder=embedder, store=store)
        self._store = store

    async def ingest(self, req: EmbedRequest) -> EmbedResponse:
        """Chunk, embed, and store a document or code file."""
        return await self._ingestor.ingest(req)

    async def retrieve(
        self,
        query: str,
        collection_id: str,
        top_k: int = 5,
        filter: dict | None = None,
    ) -> list[Chunk]:
        """Search this document's chunks for relevant content."""
        return await self._retriever.retrieve(
            query=query,
            collection_id=collection_id,
            top_k=top_k,
            filter=filter,
        )

    async def delete(self, collection_id: str) -> None:
        """Remove all vectors when a document is detached from a topic."""
        await self._store.delete_collection(collection_id)
