"""
Context Manager
---------------
Orchestrates retrieval at query time:
  user message + context source refs → search Chroma → ranked chunks

Called by the Agentic Manager before building the prompt.
"""
from __future__ import annotations

from apps.interfaces.embedding import EmbeddingModel
from apps.interfaces.vectorstore import VectorStore, Chunk
from apps.schemas.trigger import ContextSourceRef, HistoryMessage


# Max tokens we'll budget for context (rough char estimate: 1 token ≈ 4 chars)
CONTEXT_TOKEN_BUDGET = 4000
CONTEXT_CHAR_BUDGET = CONTEXT_TOKEN_BUDGET * 4


class ContextManager:
    def __init__(self, embedder: EmbeddingModel, store: VectorStore) -> None:
        self.embedder = embedder
        self.store = store

    async def retrieve(
        self,
        message: str,
        history: list[HistoryMessage],
        context_sources: list[ContextSourceRef],
        top_k: int = 5,
    ) -> list[Chunk]:
        """
        Build a search query from the current message + recent history,
        search all attached context sources in parallel, return ranked chunks
        within the token budget.
        """
        if not context_sources:
            return []

        # Build search query: current message + last 2 history turns
        recent = " ".join(m.content for m in history[-2:])
        search_query = f"{recent} {message}".strip()

        # Embed the search query
        query_vector = await self.embedder.embed_query(search_query)

        # Search all collections in parallel
        import asyncio
        tasks = [
            self.store.search(
                query_vector=query_vector,
                collection_id=src.collection_id,
                top_k=top_k,
                filter={"source_id": src.source_id},
            )
            for src in context_sources
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Flatten, filter errors, sort by score descending
        all_chunks: list[Chunk] = []
        for result in results:
            if isinstance(result, list):
                all_chunks.extend(result)

        all_chunks.sort(key=lambda c: c.score, reverse=True)

        # Apply token budget — drop lowest-scoring chunks if over limit
        selected: list[Chunk] = []
        total_chars = 0
        for chunk in all_chunks:
            chunk_chars = len(chunk.text)
            if total_chars + chunk_chars > CONTEXT_CHAR_BUDGET:
                break
            selected.append(chunk)
            total_chars += chunk_chars

        return selected
