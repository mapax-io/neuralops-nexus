"""
ChatEmbeddingManager — internal ingest logic for chat message context.
Embeds a single message and stores it in the company chat collection.
"""
from __future__ import annotations

import logging

from apps.core.config import settings
from apps.interfaces.embedding import EmbeddingModel
from apps.interfaces.vectorstore import VectorStore
from apps.schemas.embed import MessageEmbedRequest, MessageEmbedResponse

logger = logging.getLogger(__name__)


class ChatEmbeddingManager:
    def __init__(self, embedder: EmbeddingModel, store: VectorStore) -> None:
        self.embedder = embedder
        self.store = store

    async def ingest(self, req: MessageEmbedRequest) -> MessageEmbedResponse:
        """
        Embed a single chat message and store in company_{company_id}_chat.

        Uses the message UUID as ChromaDB doc ID — upsert is idempotent,
        re-embedding the same message just overwrites the old vector.

        Stores embedding_model in metadata so we can detect provider
        switches and trigger re-embedding (Task 22).
        """
        collection_name = f"company_{req.company_id}_chat"
        embedding_model = settings.EMBEDDING_MODEL

        vectors = await self.embedder.embed([req.content])

        if not vectors or not vectors[0]:
            logger.warning("[chat/embed] empty vector for message %s", req.message_id)
            return MessageEmbedResponse(
                message_id=req.message_id,
                collection=collection_name,
                embedding_model=embedding_model,
                ok=False,
            )

        metadata = {
            "company_id": req.company_id,
            "message_id": req.message_id,
            "sequence": req.sequence,
            "topic_id": req.topic_id,
            "channel_id": req.channel_id,
            "project_id": req.project_id,
            "sender_id": req.sender_id,
            "sender_name": req.sender_name,
            "sender_type": req.sender_type,
            "created_at": req.created_at,
            "embedding_model": embedding_model,
        }

        await self.store.store(
            texts=[req.content],
            vectors=[vectors[0]],
            metadatas=[metadata],
            collection_id=collection_name,
            ids=[req.message_id],
        )

        logger.info(
            "[chat/embed] stored message_id=%s seq=%s collection=%s model=%s",
            req.message_id, req.sequence, collection_name, embedding_model,
        )

        return MessageEmbedResponse(
            message_id=req.message_id,
            collection=collection_name,
            embedding_model=embedding_model,
            ok=True,
        )
