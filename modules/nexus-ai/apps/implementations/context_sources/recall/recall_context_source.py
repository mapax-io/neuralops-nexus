"""
RecallContextSource — the project's Recall (W5): what the team's personas
recorded (decisions, facts, preferences). Nucleus is the writer of record;
this plugin keeps one vector per entry in company_{company_id}_recall (doc
id = the entry id, so an edit upserts and a removal deletes by id) and
retrieves the entries relevant to a turn by project.
"""
from __future__ import annotations

import logging

from apps.core.config import settings
from apps.interfaces.context_source import ContextSource
from apps.interfaces.embedding import EmbeddingModel
from apps.interfaces.vectorstore import Chunk, VectorStore
from apps.schemas.embed import RecallEmbedRequest, RecallEmbedResponse

logger = logging.getLogger(__name__)

RECALL_LABEL = "What the team has recorded"


def recall_collection(company_id: str) -> str:
    return f"company_{company_id}_recall"


class RecallContextSource(ContextSource):
    directive = "recall"
    help = "What the team has recorded about the project — decisions, facts, preferences"

    def __init__(self, embedder: EmbeddingModel, store: VectorStore) -> None:
        self._embedder = embedder
        self._store = store

    async def ingest(self, req: RecallEmbedRequest) -> RecallEmbedResponse:
        """Embed one entry; the entry id is the doc id, so a re-embed after an edit overwrites."""
        collection = recall_collection(req.company_id)
        vectors = await self._embedder.embed([req.text])
        if not vectors or not vectors[0]:
            logger.warning("[recall/embed] empty vector for entry %s", req.entry_id)
            return RecallEmbedResponse(entry_id=req.entry_id, collection=collection, ok=False)
        metadata = {
            "type": "recall",
            "label": RECALL_LABEL,
            "entry_id": req.entry_id,
            "company_id": req.company_id,
            "project_id": req.project_id,
            "kind": req.kind,
            "author_name": req.author_name or "",
            "topic_id": req.topic_id or "",
            "created_at": req.created_at or "",
            "embedding_model": settings.EMBEDDING_MODEL,
        }
        await self._store.store(texts=[req.text], vectors=[vectors[0]], metadatas=[metadata], collection_id=collection, ids=[req.entry_id])
        return RecallEmbedResponse(entry_id=req.entry_id, collection=collection, ok=True)

    async def retrieve(self, query: str, collection_id: str, top_k: int = 8, filter: dict | None = None) -> list[Chunk]:
        """The project's entries closest to the query. The prompt builder passes {"source_id": project_id}."""
        project_id = (filter or {}).get("project_id") or (filter or {}).get("source_id")
        query_vector = await self._embedder.embed_query(query)
        return await self._store.search(
            query_vector=query_vector, collection_id=collection_id, top_k=top_k,
            filter={"project_id": project_id} if project_id else None,
        )

    async def delete_entry(self, entry_id: str, company_id: str) -> None:
        await self._store.delete_by_ids(recall_collection(company_id), [entry_id])

    async def delete(self, collection_id: str) -> None:
        await self._store.delete_collection(collection_id)
