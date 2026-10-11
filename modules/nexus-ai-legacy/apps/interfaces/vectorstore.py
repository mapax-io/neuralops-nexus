"""
VectorStore interface — every vector DB backend implements this.
Swap Chroma for Qdrant or pgvector by adding a new implementation.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class Chunk:
    """A piece of embedded content with its metadata."""
    text: str
    score: float
    metadata: dict


class VectorStore(ABC):
    """Abstract vector store."""

    @abstractmethod
    async def store(
        self,
        texts: list[str],
        vectors: list[list[float]],
        metadatas: list[dict],
        collection_id: str,
        ids: list[str] | None = None,
    ) -> None:
        """Upsert text chunks with their vectors and metadata.
        ids — optional explicit doc IDs; auto-generated if omitted.
        """
        ...

    @abstractmethod
    async def search(
        self,
        query_vector: list[float],
        collection_id: str,
        top_k: int = 5,
        filter: dict | None = None,
    ) -> list[Chunk]:
        """Search for similar chunks. Returns top_k results sorted by score."""
        ...

    @abstractmethod
    async def delete_collection(self, collection_id: str) -> None:
        """Delete all vectors for a context source (when detached from topic)."""
        ...

    @abstractmethod
    async def delete_by_ids(self, collection_id: str, ids: list[str]) -> None:
        """Delete specific documents from a collection by their IDs."""
        ...
