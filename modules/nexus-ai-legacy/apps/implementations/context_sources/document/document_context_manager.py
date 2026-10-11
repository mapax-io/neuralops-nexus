"""
DocumentContextManager — internal retrieval logic for document context.
Searches ChromaDB collections for relevant chunks at query time.
"""
from __future__ import annotations

import asyncio

from apps.interfaces.embedding import EmbeddingModel
from apps.interfaces.vectorstore import VectorStore, Chunk
from apps.schemas.trigger import ContextSourceRef, HistoryMessage

CONTEXT_TOKEN_BUDGET = 4000
CONTEXT_CHAR_BUDGET = CONTEXT_TOKEN_BUDGET * 4


class DocumentContextManager:
    def __init__(self, embedder: EmbeddingModel, store: VectorStore) -> None:
        self.embedder = embedder
        self.store = store

    async def retrieve(
        self,
        query: str,
        collection_id: str,
        top_k: int = 5,
        filter: dict | None = None,
        history: list[HistoryMessage] | None = None,
    ) -> list[Chunk]:
        """
        Embed the query (optionally enriched with recent history),
        search the document collection, return ranked chunks within budget.
        """
        # Enrich query with last 2 history turns for better recall
        if history:
            recent = " ".join(m.content for m in history[-2:])
            search_query = f"{recent} {query}".strip()
        else:
            search_query = query

        query_vector = await self.embedder.embed_query(search_query)

        chunks = await self.store.search(
            query_vector=query_vector,
            collection_id=collection_id,
            top_k=top_k,
            filter=filter,
        )

        # Apply token budget
        selected: list[Chunk] = []
        total_chars = 0
        for chunk in sorted(chunks, key=lambda c: c.score, reverse=True):
            if total_chars + len(chunk.text) > CONTEXT_CHAR_BUDGET:
                break
            selected.append(chunk)
            total_chars += len(chunk.text)

        return selected
