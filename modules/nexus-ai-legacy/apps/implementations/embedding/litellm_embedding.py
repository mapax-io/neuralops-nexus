"""
LiteLLM embedding implementation.
Same provider routing as the LLM — no local model downloads.
Configure via EMBEDDING_MODEL env var:
  ollama/nomic-embed-text       (default — via Ollama service)
  openai/text-embedding-3-small
  cohere/embed-english-v3.0
  etc.
"""
from __future__ import annotations

import litellm
from apps.interfaces.embedding import EmbeddingModel
from apps.core.config import settings


class LiteLLMEmbedding(EmbeddingModel):
    def __init__(self, model: str = "ollama/nomic-embed-text") -> None:
        self.model = model
        # Pass api_base for Ollama so LiteLLM knows where to reach it.
        self._api_base = settings.OLLAMA_BASE_URL if model.startswith("ollama/") else None

    async def embed(self, texts: list[str]) -> list[list[float]]:
        kwargs: dict = dict(model=self.model, input=texts)
        if self._api_base:
            kwargs["api_base"] = self._api_base
        response = await litellm.aembedding(**kwargs)
        return [item["embedding"] for item in response.data]

    async def embed_query(self, text: str) -> list[float]:
        vectors = await self.embed([text])
        return vectors[0]
