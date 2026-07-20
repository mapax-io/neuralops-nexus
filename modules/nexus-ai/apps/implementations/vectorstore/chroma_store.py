"""
Chroma vector store implementation.
chromadb.HttpClient is synchronous — all blocking calls are wrapped with
asyncio.to_thread() so they don't block the FastAPI event loop.
"""
from __future__ import annotations

import asyncio
import chromadb
from apps.interfaces.vectorstore import VectorStore, Chunk


class ChromaStore(VectorStore):
    def __init__(self, host: str = "localhost", port: int = 8000) -> None:
        self.client = chromadb.HttpClient(host=host, port=port)

    def _collection(self, collection_id: str):
        return self.client.get_or_create_collection(name=collection_id)

    async def store(
        self,
        texts: list[str],
        vectors: list[list[float]],
        metadatas: list[dict],
        collection_id: str,
        ids: list[str] | None = None,
    ) -> None:
        """
        Upsert documents into a Chroma collection.

        ids — optional explicit document IDs.
              If omitted, IDs are auto-generated as {collection_id}_{i}.
              Pass explicit IDs (e.g. message UUIDs) to make upserts idempotent:
              re-embedding the same document will overwrite the existing vector.
        """
        doc_ids = ids if ids else [f"{collection_id}_{i}" for i in range(len(texts))]

        def _upsert():
            collection = self._collection(collection_id)
            # upsert = add-or-update; safe to call multiple times for the same ID
            collection.upsert(
                ids=doc_ids,
                documents=texts,
                embeddings=vectors,
                metadatas=metadatas,
            )

        await asyncio.to_thread(_upsert)

    async def search(
        self,
        query_vector: list[float],
        collection_id: str,
        top_k: int = 5,
        filter: dict | None = None,
    ) -> list[Chunk]:
        def _query():
            collection = self._collection(collection_id)
            kwargs: dict = dict(
                query_embeddings=[query_vector],
                n_results=top_k,
            )
            if filter:
                kwargs["where"] = filter
            return collection.query(**kwargs)

        results = await asyncio.to_thread(_query)

        chunks = []
        for i, doc in enumerate(results["documents"][0]):
            chunks.append(Chunk(
                text=doc,
                score=1 - results["distances"][0][i],  # distance → similarity score
                metadata=results["metadatas"][0][i],
            ))
        return chunks

    async def delete_collection(self, collection_id: str) -> None:
        await asyncio.to_thread(self.client.delete_collection, collection_id)
