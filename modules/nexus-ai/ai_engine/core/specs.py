"""
The engine's data classes — plain Python, frozen, no framework.
Shapes are the Layer 0 spec in docs/NEXUS-AI-REVAMP.md §1.5.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Literal

from fastapi_app.contracts.trigger import TriggerJob


class ModelRole(Enum):
    ROUTER = "ROUTER"
    STANDARD = "STANDARD"
    DEEP = "DEEP"
    FALLBACK = "FALLBACK"


@dataclass(frozen=True)
class ModelSpec:
    """One model endpoint, ready to use. context_window is the INPUT ceiling and
    is never the same field as the persona's output limit (Appendix A defect)."""

    role: ModelRole
    config_id: str            # ModelInternal.id
    name: str
    provider: str             # openai | anthropic | google | ollama | openai_compatible
    model_id: str             # bare name, no prefix
    base_url: str | None
    api_key: str | None
    context_window: int
    supports_tools: bool
    supports_streaming: bool
    supports_vision: bool


@dataclass(frozen=True)
class PersonaSpec:
    """The persona unfolded fully from day one (§1.3): all models with roles,
    tools with levels — even though Layer 0 uses one model and no tools."""

    id: str
    name: str
    company_id: str
    project_id: str
    system_prompt: str                # PromptInternal.system_prompt
    project_brief: str | None         # goes ahead of the persona prompt
    output_type: str                  # kept, unused in L0
    context_scope: list | None        # kept, unused in L0
    temperature: float
    max_output_tokens: int            # PersonaInternal.max_tokens — the OUTPUT cap
    max_steps: int                    # kept, unused in L0
    models: tuple[ModelSpec, ...]     # model → STANDARD; fallback_models → FALLBACK, in order
    advisor_model: ModelSpec | None   # kept, unused in L0
    utility_model: ModelSpec | None   # kept, unused in L0
    tool_levels: dict                 # kept, unused in L0
    mcp_servers: tuple[dict, ...]     # kept raw, unused in L0
    capabilities: tuple[dict, ...]    # kept raw, unused in L0
    recall_enabled: bool              # kept, unused in L0

    def model_for(self, role: ModelRole) -> ModelSpec:
        """The persona's first model with this role; raises if it has none."""
        for spec in self.models:
            if spec.role is role:
                return spec
        raise LookupError(f"persona {self.id} has no model with role {role.value}")


@dataclass(frozen=True)
class HistoryRow:
    """HistoryMessageInternal as nucleus sends it (NU/internal/api.py)."""

    id: str
    sender_type: str          # "human" | "persona" | "system"
    sender_name: str | None
    content: str
    render_as: str
    output_type: str
    stopped: bool
    sequence: int
    status: str | None = None  # new field from nucleus change (2); None from an older nucleus


@dataclass(frozen=True)
class HistoryMessage:
    role: Literal["user", "assistant"]
    author: str | None
    text: str                 # already attributed (see HistoryPolicy)


@dataclass(frozen=True)
class ContextBundle:
    history: tuple[HistoryMessage, ...]   # L3 adds retrieval fields


@dataclass(frozen=True)
class PromptSection:
    kind: str                 # "project_brief" | "persona_prompt" | ...
    priority: int             # higher = dropped last (L2 BudgetFitter)
    stable: bool              # True = same every turn → goes first (cache)
    text: str


@dataclass(frozen=True)
class PromptPlan:
    instructions: tuple[PromptSection, ...]  # joined into the single instructions= string
    history: tuple[HistoryMessage, ...]
    message: str


@dataclass(frozen=True)
class ReplyRequest:
    job: TriggerJob
    persona: PersonaSpec
    role: ModelRole           # STANDARD in L0
    plan: PromptPlan


@dataclass(frozen=True)
class UsageRecord:
    """One model call's usage. Counts follow pydantic-ai semantics (§1.3 Billing):
    input_tokens INCLUDES cache read + write; output_tokens INCLUDES reasoning.
    Cost is filled where prices live (O1: nucleus) — Decimal, never float."""

    # who / where
    company_id: str
    project_id: str
    topic_id: str
    persona_id: str
    user_id: str
    message_id: str
    job_id: str
    # what
    kind: str                 # "chat_reply" in L0
    model_config_id: str
    provider: str
    model_id: str
    role: str
    provider_response_id: str | None
    # counts
    input_tokens: int         # total, incl. cache read + write
    uncached_input_tokens: int
    cache_read_tokens: int
    cache_write_5m_tokens: int
    cache_write_1h_tokens: int
    output_tokens: int        # total, incl. reasoning
    reasoning_tokens: int     # part of output_tokens, never added on top
    finish_reason: str | None
    estimated: bool
    called_at: datetime       # UTC; the price in force at this moment applies
    # cost — filled where prices live (O1); Decimal, never float
    cost: Decimal | None = None
    prices_used: dict | None = None
