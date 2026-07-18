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
    # Options: "litellm" | "openai" | "anthropic" | "ollama"
    LLM_PROVIDER: str = "litellm"
    # Full model string passed to LiteLLM (provider/model-id format).
    # Examples: "anthropic/claude-haiku-4-5-20251001", "openai/gpt-4o-mini"
    LLM_MODEL: str = "anthropic/claude-haiku-4-5-20251001"

    # ── Embedding ─────────────────────────────────────────────────────────────
    # Options: "litellm" | "openai" | "ollama" | "fastembed"
    # "litellm" routes through LiteLLM — no local model downloads.
    # Model format examples:
    #   "ollama/nomic-embed-text"        ← default (Ollama docker service)
    #   "openai/text-embedding-3-small"  (needs OpenAI key with embedding access)
    EMBEDDING_PROVIDER: str = "litellm"
    EMBEDDING_MODEL: str = "ollama/nomic-embed-text"

    # ── Vector store ──────────────────────────────────────────────────────────
    # Options: "chroma" | "qdrant" | "pgvector"
    VECTOR_STORE: str = "chroma"
    CHROMA_HOST: str = "nexus-chroma"
    CHROMA_PORT: int = 8000

    # ── API keys / endpoints ──────────────────────────────────────────────────
    OPENAI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    # Points to the Ollama docker service; override in .env if running locally.
    OLLAMA_BASE_URL: str = "http://nexus-ollama:11434"

    # ── Internal auth (nexus-nucleus → nexus-ai calls) ───────────────────────
    INTERNAL_API_KEY: str = "change-me-in-production"

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
