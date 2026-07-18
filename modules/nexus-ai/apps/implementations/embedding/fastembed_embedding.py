"""
FastEmbed implementation — local embeddings, no API key required.
Uses BAAI/bge-small-en-v1.5 by default (fast, good quality, 384 dims).
"""
from __future__ import annotations

from apps.interfaces.embedding import EmbeddingModel


class FastEmbedEmbedding(EmbeddingModel):
    def __init__(self, model: str = "BAAI/bge-small-en-v1.5") -> None:
        from fastembed import TextEmbedding
        self._model = TextEmbedding(model_name=model)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        # fastembed is sync — returns a generator
        return [vec.tolist() for vec in self._model.embed(texts)]

    async def embed_query(self, text: str) -> list[float]:
        vectors = await self.embed([text])
        return vectors[0]
