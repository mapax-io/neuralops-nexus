"""
ContextSource — abstract plugin interface.

Every context type (document, chat, web, database, ...) implements this.
The system talks ONLY to this interface — never to internals.

Plugin structure:
    implementations/context_sources/{type}/
        {type}_context_source.py   ← implements ContextSource (entry point)
        {type}_embedding_manager.py ← internal: ingest logic
        {type}_context_manager.py   ← internal: retrieval logic

To add a new context type:
    1. Drop a folder under implementations/context_sources/
    2. Implement ContextSource
    3. Register one line in ContextSourceFactory
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from apps.interfaces.vectorstore import Chunk


class ContextSource(ABC):
    """
    Abstract base for all context source plugins.
    Each plugin owns its full lifecycle: ingest, retrieve, delete.
    """

    @abstractmethod
    async def ingest(self, req: Any) -> Any:
        """
        Embed and store content into the vector DB.
        req type and return type are defined by each plugin's schema.
        """
        ...

    @abstractmethod
    async def retrieve(
        self,
        query: str,
        collection_id: str,
        top_k: int = 5,
        filter: dict | None = None,
    ) -> list[Chunk]:
        """
        Embed the query and search the vector DB.
        Returns ranked chunks within token budget.
        """
        ...

    @abstractmethod
    async def delete(self, collection_id: str) -> None:
        """Remove all vectors for this context source."""
        ...
