"""
DocumentEmbeddingManager — internal ingest logic for document context.
Handles chunking, embedding, and storing documents/code files.
"""
from __future__ import annotations

import uuid

from apps.interfaces.embedding import EmbeddingModel
from apps.interfaces.vectorstore import VectorStore
from apps.factories.adapter import AdapterFactory
from apps.schemas.embed import EmbedRequest, EmbedResponse


class DocumentEmbeddingManager:
    def __init__(self, embedder: EmbeddingModel, store: VectorStore) -> None:
        self.embedder = embedder
        self.store = store

    async def ingest(self, req: EmbedRequest) -> EmbedResponse:
        """
        Full ingest pipeline for one document/code context source.
        content → adapter (extract + chunk) → embed → store
        Returns collection_id to save back in nexus-nucleus ContextSource.
        """
        # 1. Extract text chunks via the right adapter
        adapter = AdapterFactory.get(req.type)
        chunks = await adapter.extract(
            content=req.content,
            metadata={"language": req.language, "label": req.label},
        )

        if not chunks:
            chunks = [req.content]  # fallback: treat whole content as one chunk

        # 2. Embed all chunks
        vectors = await self.embedder.embed(chunks)

        # 3. Build metadata per chunk
        collection_id = str(uuid.uuid4())
        metadatas = [
            {
                "source_id": req.source_id,
                "type": req.type,
                "label": req.label,
                "language": req.language,
                "chunk_index": i,
                "topic_id": req.topic_id or "",
                "channel_id": req.channel_id or "",
                "project_id": req.project_id or "",
                "company_id": req.company_id or "",
            }
            for i in range(len(chunks))
        ]

        # 4. Store in vector DB
        await self.store.store(
            texts=chunks,
            vectors=vectors,
            metadatas=metadatas,
            collection_id=collection_id,
        )

        return EmbedResponse(
            source_id=req.source_id,
            collection_id=collection_id,
            chunks_count=len(chunks),
        )
