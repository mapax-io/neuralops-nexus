"""
The wire contract with nucleus — TriggerJob in, AgentEvent out.

Field names are kept exactly as 0.8.0 sends and reads them
(nexus-ai-legacy/apps/schemas/trigger.py), so nucleus keeps working.
Three new optional ids (company_id, project_id, user_id) are O2 in
docs/NEXUS-AI-REVAMP.md §1.5: today's nucleus does not send them, so they
default to "" and the reply works either way; usage records carry whatever
arrived.

These are plain pydantic data classes: framework-neutral, Django could use
them too. ai_engine imports this module and nothing else of fastapi_app.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class ContextSourceRef(BaseModel):
    """One attached context source, pushed by nucleus inside the job (0.8.0 shape)."""

    source_id: str
    type: str  # "doc" | "code" | "chat" | "recall"
    label: str
    language: str | None = None
    collection_id: str


class TriggerJob(BaseModel):
    """
    What nucleus sends to POST /api/v1/trigger/.

    Layer 0 uses: job_id, msg_id, persona_id, topic_id, user_message_id,
    message, and the three new ids. Everything else (context_sources,
    output_type, and the five unplaced-feature fields) is accepted and
    ignored, per §1.3 "Entry point and request flow".
    """

    job_id: str
    msg_id: str  # pre-generated reply id — echoed on every event, used by nucleus for the DB save
    persona_id: str
    topic_id: str
    user_message_id: str  # the human message being answered; excluded from history
    message: str

    # O2 (nucleus change 4): absent from today's nucleus, so they default.
    company_id: str = ""
    project_id: str = ""
    user_id: str = ""

    # Accepted and ignored in Layer 0 — kept so the 0.8.0 payload validates.
    context_sources: list[ContextSourceRef] = Field(default_factory=list)
    output_type: str = "auto"
    preflight: bool = False
    approved_plan: str | None = None
    interactive: bool = True
    routine_id: str | None = None
    step_context: str | None = None


class AgentEventType(str, Enum):
    START = "message_start"
    DELTA = "message_delta"
    END = "message_done"
    ERROR = "message_error"
    KEEPALIVE = "keepalive"


class AgentEvent(BaseModel):
    """
    What goes back over SSE. Layer 0 sends five types; names and fields match
    what the 0.8.0 nucleus relay reads (NU/chat/services.py):
      every event   — type, id (= msg_id), persona_id, persona_name, created_at
      message_delta — delta
      message_done  — content, output_type, render_as, answered_by_model,
                      prompt_tokens, output_tokens, context_window
      message_error — error, error_code
    """

    type: AgentEventType
    id: str  # msg_id

    created_at: str | None = None
    persona_id: str | None = None
    persona_name: str | None = None

    # message_delta only
    delta: str | None = None

    # message_done only
    content: str | None = None
    output_type: str | None = None
    render_as: str | None = None
    answered_by_model: str | None = None
    prompt_tokens: int | None = None   # = input_tokens total (incl. cache read + write)
    output_tokens: int | None = None   # total, incl. reasoning
    context_window: int | None = None

    # message_error only
    error: str | None = None
    error_code: str | None = None
