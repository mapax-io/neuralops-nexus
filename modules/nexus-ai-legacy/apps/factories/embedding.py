"""
EmbeddingFactory — returns the right EmbeddingModel based on config.

Two providers:
  fastembed  — local ONNX, runs inside nexus-ai, no network, no GPU.
               Default. Model: nomic-ai/nomic-embed-text-v1.5
  litellm    — routes to any remote embedding service via LiteLLM.
               Set EMBEDDING_MODEL to provider-prefixed string:
               e.g. "ollama/nomic-embed-text", "openai/text-embedding-3-small"
               Set EMBEDDING_BASE_URL if needed (Ollama, Infinity, etc.)

Switch provider via EMBEDDING_PROVIDER env var — zero code changes.
"""
from apps.interfaces.embedding import EmbeddingModel
from apps.core.config import settings


class EmbeddingFactory:
    @staticmethod
    def get(provider: str | None = None) -> EmbeddingModel:
        provider = provider or settings.EMBEDDING_PROVIDER

        match provider:
            case "fastembed":
                from apps.implementations.embedding.fastembed_embedding import FastEmbedEmbedding
                return FastEmbedEmbedding(model=settings.EMBEDDING_MODEL)

            case "litellm":
                from apps.implementations.embedding.litellm_embedding import LiteLLMEmbedding
                return LiteLLMEmbedding(
                    model=settings.EMBEDDING_MODEL,
                    api_base=settings.EMBEDDING_BASE_URL or None,
                )

            case _:
                raise ValueError(
                    f"Unknown embedding provider: {provider!r}. "
                    f"Valid options: 'fastembed', 'litellm'"
                )
