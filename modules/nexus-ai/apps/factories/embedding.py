"""
EmbeddingFactory — returns the right EmbeddingModel based on config.
All providers go through LiteLLM by default — no local model downloads.
"""
from apps.interfaces.embedding import EmbeddingModel
from apps.core.config import settings


class EmbeddingFactory:
    @staticmethod
    def get(provider: str | None = None) -> EmbeddingModel:
        provider = provider or settings.EMBEDDING_PROVIDER

        match provider:
            case "litellm":
                from apps.implementations.embedding.litellm_embedding import LiteLLMEmbedding
                return LiteLLMEmbedding(model=settings.EMBEDDING_MODEL)

            case "openai":
                from apps.implementations.embedding.litellm_embedding import LiteLLMEmbedding
                return LiteLLMEmbedding(model=f"openai/{settings.EMBEDDING_MODEL}")

            case "ollama":
                from apps.implementations.embedding.litellm_embedding import LiteLLMEmbedding
                return LiteLLMEmbedding(model=f"ollama/{settings.EMBEDDING_MODEL}")

            case "fastembed":
                from apps.implementations.embedding.fastembed_embedding import FastEmbedEmbedding
                return FastEmbedEmbedding(model=settings.EMBEDDING_MODEL)

            case _:
                raise ValueError(f"Unknown embedding provider: {provider!r}")
