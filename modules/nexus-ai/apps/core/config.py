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

    # ── nexus-nucleus base URL (nexus-ai → nexus-nucleus calls) ───────────────
    # "nucleus" -- nucleus's docker-compose *service* name, not its
    # container_name (nexus-nucleus). Compose only guarantees the service
    # name resolves over the network's embedded DNS; container_name is
    # just a docker ps label unless it happens to also line up. Override
    # via env var in non-Compose setups.
    NEXUS_NUCLEUS_URL: str = "http://nucleus:8000"

    # ── Prompt tuning ─────────────────────────────────────────────────────────
    # How many past messages to pull as conversation history per trigger.
    # Lives here, not in nexus-nucleus, on purpose -- this is a prompt-quality
    # knob (see apps/managers/nucleus_client.py:fetch_history), tunable without
    # a nexus-nucleus deploy.
    HISTORY_DEPTH: int = 20

    # ── Tool approvals (apps/managers/approvals.py) ───────────────────────────
    # How long an Ask tool waits for a person before it is skipped, and how
    # often the worker asks nucleus whether someone decided.
    APPROVAL_TIMEOUT_SECONDS: float = 600
    APPROVAL_POLL_SECONDS: float = 1.0
    # A keepalive goes out after this much silence on the event stream; the
    # relay reads with a two-minute idle timeout.
    STREAM_KEEPALIVE_SECONDS: float = 30

    # ── Terminal (apps/managers/terminal.py) ─────────────────────────────────
    # The shell a Terminal pane session runs, how long one may sit without
    # input, and how many may be open on this worker at once.
    # ── The live browser (a real Chromium on the server, streamed to the app) ──
    # Off unless the image was built with it; nucleus asks before offering the pane.
    BROWSER_ENABLED: bool = True
    BROWSER_HOME: str = "https://duckduckgo.com"
    BROWSER_MAX_TABS: int = 8
    BROWSER_MAX_SESSIONS: int = 4
    BROWSER_MAX_WIDTH: int = 1920
    BROWSER_MAX_HEIGHT: int = 1200
    BROWSER_FRAME_QUALITY: int = 60
    BROWSER_NAV_TIMEOUT_MS: int = 30_000
    BROWSER_IDLE_SECONDS: int = 900
    BROWSER_USER_AGENT: str = ""
    # Where a project's browser keeps its cookies and local storage between
    # sessions (a login, a challenge already passed). Outside the project
    # folder on purpose: personas' file tools can read that, and a cookie jar
    # is not theirs to read. Mounted as a volume in compose so it survives
    # the container.
    BROWSER_STATE_DIR: str = "/home/nexus/.cache/neuralops-browser"
    # Run the browser windowed on a virtual display (Xvfb, in the image) rather
    # than in headless mode. Off, or with no Xvfb on the image, it runs the
    # full Chromium headless instead.
    BROWSER_WINDOWED: bool = True
    BROWSER_DISPLAY: str = ":99"
    # A browser INSIDE the deployment must not be a way to reach the database or
    # a cloud metadata endpoint. Turn on only for a server with nothing private.
    BROWSER_ALLOW_PRIVATE_NETWORK: bool = False

    TERMINAL_SHELL: str = "/bin/bash"
    TERMINAL_IDLE_SECONDS: int = 1800
    TERMINAL_MAX_SESSIONS: int = 20
    # How long a model check (apps/managers/model_check.py) waits for the model.
    MODEL_CHECK_TIMEOUT_SECONDS: float = 20
    # Recall (W5): entries retrieved per turn, and how long the remember pass may take.
    RECALL_TOP_K: int = 8
    RECALL_REMEMBER_TIMEOUT_SECONDS: float = 15
    # Nudge (W8): the poll after each tool call must not slow the run.
    NUDGE_POLL_TIMEOUT_SECONDS: float = 1.5
    # Runbooks (W6): how much of the previous step's reply a step is given (its head).
    RUNBOOK_STEP_CONTEXT_MAX: int = 12_000

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
