"""Ollama embedding implementation (local, free, private)."""
from __future__ import annotations

import httpx
from apps.interfaces.embedding import EmbeddingModel


class OllamaEmbedding(EmbeddingModel):
    def __init__(
        self,
        model: str = "nomic-embed-text",
        base_url: str = "http://localhost:11434",
    ) -> None:
        self.model = model
        self.base_url = base_url

    async def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        async with httpx.AsyncClient() as client:
            for text in texts:
                response = await client.post(
                    f"{self.base_url}/api/embeddings",
                    json={"model": self.model, "prompt": text},
                    timeout=30,
                )
                response.raise_for_status()
                vectors.append(response.json()["embedding"])
        return vectors

    async def embed_query(self, text: str) -> list[float]:
        vectors = await self.embed([text])
        return vectors[0]
