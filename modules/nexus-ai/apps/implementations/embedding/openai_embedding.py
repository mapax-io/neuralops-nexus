"""OpenAI embedding implementation."""
from __future__ import annotations

import openai
from apps.interfaces.embedding import EmbeddingModel


class OpenAIEmbedding(EmbeddingModel):
    def __init__(self, model: str = "text-embedding-3-small") -> None:
        self.model = model
        self.client = openai.AsyncOpenAI()

    async def embed(self, texts: list[str]) -> list[list[float]]:
        response = await self.client.embeddings.create(
            model=self.model,
            input=texts,
        )
        return [item.embedding for item in response.data]

    async def embed_query(self, text: str) -> list[float]:
        vectors = await self.embed([text])
        return vectors[0]
