"""Schemas for the /trigger/ endpoint (nexus-nucleus → nexus-ai) and SSE events."""
from pydantic import BaseModel


# ── Inbound job payload ────────────────────────────────────────────────────────

class ModelConfig(BaseModel):
    provider: str                    # "litellm" | "local"
    model_id: str                    # "anthropic/claude-haiku-4-5-20251001"
    api_key: str | None = None       # decrypted key from AIModel — passed per-call
    max_tokens: int = 4096
    temperature: float = 0.7
    supports_vision: bool = False


class PersonaConfig(BaseModel):
    id: str
    name: str                        # "NeuralBot"
    system_prompt: str
    model: ModelConfig


class HistoryMessage(BaseModel):
    role: str                        # "user" | "assistant"
    content: str
    sender_name: str | None = None   # display only, not sent to LLM


class ContextSourceRef(BaseModel):
    source_id: str
    type: str                        # "doc" | "code"
    label: str                       # "auth.py"
    language: str | None = None
    collection_id: str               # Chroma collection to search


class TriggerJob(BaseModel):
    job_id: str
    msg_id: str                      # pre-generated UUID — used in SSE events + DB save

    persona: PersonaConfig
    message: str                     # the user's current message (mentions stripped)
    history: list[HistoryMessage] = []
    context_sources: list[ContextSourceRef] = []

    # M7: output type — resolved in nexus-nucleus from @mention detection.
    # "auto" = nexus-ai should classify intent via cosine similarity.
    # Any other value = explicit override (e.g. "chart", "terminal", "code").
    output_type: str = "auto"


# ── Outbound SSE events (nexus-ai → nexus-nucleus) ────────────────────────────

class AgentEvent(BaseModel):
    type: str                        # "message_start" | "message_delta" | "message_done"
    id: str                          # msg_id

    # message_start only
    created_at: str | None = None

    # message_delta only
    delta: str | None = None

    # message_done only
    content: str | None = None       # full assembled response (markers stripped) for DB save

    # M7: output type metadata — populated in message_done
    output_type: str | None = None   # resolved type: "chart", "terminal", "text", etc.
    render_as: str | None = None     # renderer hint: "html" | "code" | "text" | "terminal"
