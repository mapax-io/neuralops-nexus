"""
EmbeddingModel interface — every embedding backend implements this.
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class EmbeddingModel(ABC):
    """Abstract embedding model."""

    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """
        Embed a list of text strings.
        Returns a list of float vectors, one per input text.
        """
        ...

    @abstractmethod
    async def embed_query(self, text: str) -> list[float]:
        """Embed a single query string. Returns one float vector."""
        ...
