"""
nexus-ai configuration — driven entirely by environment variables.
Swap any backend by changing a single env var, zero code changes.
"""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── Agent backend ─────────────────────────────────────────────────────────
    # Options: "pydantic_ai" | "agno" | "langgraph"
    AGENT_BACKEND: str = "pydantic_ai"

    # ── LLM ──────────────────────────────────────────────────────────────────
    # All LLM calls go through LiteLLM — one gateway for all providers.
    # Encode the provider in LLM_MODEL using LiteLLM's prefix format:
    #   "anthropic/claude-haiku-4-5-20251001"
    #   "openai/gpt-4o"
    #   "azure/gpt-4"
    #   "ollama/llama3"  (set OLLAMA_BASE_URL for the Ollama service)
    LLM_PROVIDER: str = "litellm"
    LLM_MODEL: str = "anthropic/claude-haiku-4-5-20251001"

    # ── Embedding ─────────────────────────────────────────────────────────────
    # Options: "fastembed" | "litellm"
    #   fastembed  — local ONNX, runs inside nexus-ai, no network, no GPU (default)
    #   litellm    — routes to any remote service; set EMBEDDING_MODEL with prefix:
    #                "ollama/nomic-embed-text", "openai/text-embedding-3-small"
    #                Set EMBEDDING_BASE_URL if needed (Ollama, Infinity, etc.)
    EMBEDDING_PROVIDER: str = "fastembed"
    EMBEDDING_MODEL: str = "nomic-ai/nomic-embed-text-v1.5"
    EMBEDDING_BASE_URL: str = ""

    # ── Vector store ──────────────────────────────────────────────────────────
    # Options: "chroma" | "qdrant" | "pgvector"
    VECTOR_STORE: str = "chroma"
    CHROMA_HOST: str = "nexus-chroma"
    CHROMA_PORT: int = 8000

    # ── API keys / endpoints ──────────────────────────────────────────────────
    OPENAI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    # Ollama service URL — only needed when EMBEDDING_PROVIDER=litellm
    # and EMBEDDING_MODEL starts with "ollama/", or LLM_MODEL starts with "ollama/"
    OLLAMA_BASE_URL: str = "http://nexus-ollama:11434"

    # ── Internal auth (nexus-nucleus → nexus-ai calls) ───────────────────────
    INTERNAL_API_KEY: str = "change-me-in-production"

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
