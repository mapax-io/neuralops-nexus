"""
ContextAdapter interface — every context type (doc, code) implements this.
Adapters extract clean text from raw source content for chunking + embedding.
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class ContextAdapter(ABC):
    """
    Abstract context adapter.
    Transforms raw source content into a list of clean text strings
    ready for chunking and embedding.
    """

    @abstractmethod
    async def extract(
        self,
        content: str,
        metadata: dict | None = None,
    ) -> list[str]:
        """
        Extract text from raw content.
        Returns a list of text chunks (pre-split by natural boundaries
        e.g. paragraphs for docs, functions for code).
        """
        ...
