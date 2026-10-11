"""
ChatContextManager — internal retrieval logic for chat message context.
Searches the company chat collection for semantically similar past messages.
"""
from __future__ import annotations

from apps.interfaces.embedding import EmbeddingModel
from apps.interfaces.vectorstore import VectorStore, Chunk


class ChatContextManager:
    def __init__(self, embedder: EmbeddingModel, store: VectorStore) -> None:
        self.embedder = embedder
        self.store = store

    async def retrieve(
        self,
        query: str,
        collection_id: str,
        top_k: int = 10,
        filter: dict | None = None,
    ) -> list[Chunk]:
        """
        Search past chat messages semantically similar to the query.

        collection_id should be company_{company_id}_chat.
        filter can narrow by topic_id, sender_id, sender_type, etc.

        Returns messages sorted by similarity score, highest first.
        """
        query_vector = await self.embedder.embed_query(query)

        return await self.store.search(
            query_vector=query_vector,
            collection_id=collection_id,
            top_k=top_k,
            filter=filter,
        )
