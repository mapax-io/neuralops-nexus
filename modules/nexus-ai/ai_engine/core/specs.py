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
    # 7b (owner's ruling 2026-10-20): generation settings are MODEL properties.
    # Defaults keep an OLDER nucleus (which doesn't send them) working — the
    # persona-level numbers then stand in (see PersonaSpec.limits_for).
    max_output_tokens: int = 16000
    temperature: float = 0.7
    # The strengths/weaknesses line the smart router reads (next build).
    routing_notes: str = ""


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
    # Item 3/4 (nucleus change 7): "selected" = exactly the attached servers
    # (today's behaviour, and the value when nucleus doesn't send the field);
    # "all_project" is resolved in NUCLEUS — nexus-ai still just reads the list.
    tool_access: str = "selected"
    # Item 2 (decision 5, 2026-10-12): who may answer an approval — "topic"
    # (anyone holding persona.approve_run there) or "requester_only". ENFORCED
    # BY NUCLEUS on the approval path; carried here so one object holds the
    # persona's whole trust rule.
    approval_scope: str = "topic"
    # Item 46 (Layer 6): nucleus's supervisor checkbox — this persona may run
    # other personas through call_persona (handoff change 14).
    delegation_enabled: bool = False

    def model_for(self, role: ModelRole) -> ModelSpec:
        """The persona's first model with this role; raises if it has none."""
        for spec in self.models:
            if spec.role is role:
                return spec
        raise LookupError(f"persona {self.id} has no model with role {role.value}")

    def model_for_or_none(self, role: ModelRole) -> ModelSpec | None:
        """Like model_for, but an empty seat is None, not an error (item 13:
        the ROUTER/DEEP seats are optional; behaviour falls out of which seats
        the admin filled)."""
        for spec in self.models:
            if spec.role is role:
                return spec
        return None

    def models_for(self, role: ModelRole) -> tuple[ModelSpec, ...]:
        """EVERY model with this role, in order. The DEEP seat is a BENCH
        (smart router, ruled 2026-10-20): the router picks one by its
        routing_notes, and the FIRST is the default pick."""
        return tuple(spec for spec in self.models if spec.role is role)


@dataclass(frozen=True)
class ToolCatalogEntry:
    """One tool a persona could use (item 3). tool_id is the levels/catalog key
    ("mcp:<server_id>/<tool>", "mcp:<server_id>" for a server whose tools are
    not stored yet, or "<capability>" for natives); model_name is what the
    MODEL calls it — server-slug-prefixed so two servers' same-named tools
    never collide (github__search)."""

    tool_id: str
    model_name: str
    source_id: str
    source_kind: str          # "native" | "mcp"
    one_line: str
    read_only: bool | None


@dataclass(frozen=True)
class LoadedSet:
    """The topic's loaded tools (item 1): fixed per topic, stored by nucleus,
    shipped in TriggerJob.topic_tools. catalog_hash fingerprints the catalog
    the set was decided against."""

    tool_ids: tuple[str, ...]
    catalog_hash: str


@dataclass(frozen=True)
class PendingApproval:
    """One tool call waiting on a person (item 2; item 5 reuses the shape)."""

    call_id: str
    tool: str            # the MODEL-facing name (write_file, github__search)
    capability_id: str
    args_preview: str    # ≤300 chars (decision 7); full args are in the state
    # item 5: "approval" = decide yes/no; "question" = ask_user, the resume
    # carries the person's ANSWER (ResumeBlock.answers) instead of a decision.
    kind: str = "approval"


@dataclass(frozen=True)
class PauseInfo:
    """Everything a resume needs (item 2 / item 27): the run's messages as
    JSON (ModelMessagesTypeAdapter) plus the pending calls. POSTed to nucleus
    at pause time; comes back verbatim in TriggerJob.resume.state."""

    state: str
    pending: tuple[PendingApproval, ...]
    catalog_hash: str


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
    # Item 23: the row's output type — the resolver's pick logic needs to find
    # the last "choice" reply ("text" from an older nucleus, harmless).
    output_type: str = "text"


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
    # Item 13: why this call happened when it wasn't the normal path —
    # "router_failed" on a router call that errored/timed out (the reply then
    # fell through to STANDARD); None otherwise.
    source: str | None = None
    # cost — filled where prices live (O1); Decimal, never float
    cost: Decimal | None = None
    prices_used: dict | None = None


# ── Layer 3 (items 31/44/24/33): the vector store's own shapes ────────────
# Framework-free on purpose: ai_engine/vector_db/ implements them with txtai,
# nothing outside that folder may import txtai (§1.3 quarantine, decision 1).

@dataclass(frozen=True)
class VectorItem:
    """One row to index: a message, a document chunk, or a recall entry.
    `text` is stored raw beside the vector (decision 4 — a re-embed never
    re-fetches sources); `source` groups rows for delete-by-source."""

    id: str                    # message_id | "{source_id}:{n}" | entry_id
    kind: str                  # "message" | "context_source" | "recall" | "tool_result"
    text: str
    label: str                 # human-readable ("auth.py", sender name, tool+command, …)
    source: str                # delete key ("chat:{topic}", "src:{source_id}", "recall:{entry_id}", "toolres:{msg_id}")
    topic_id: str | None = None
    used_tools: tuple[str, ...] = ()   # item 44: what solved the remembered answer
    created_at: str = ""       # item 27: when the memory was made (staleness label)


@dataclass(frozen=True)
class SearchQuery:
    """One scoped search (decision 9): company+project always; topic_id narrows
    chat memory to the SAME topic (item 44's rule); kinds narrows by row kind."""

    company_id: str
    project_id: str
    text: str
    topic_id: str | None = None
    kinds: tuple[str, ...] = ()
    top_k: int = 6
    min_score: float = 0.30


@dataclass(frozen=True)
class SearchHit:
    """One result: reference + score + the stored text. The EVENT carries only
    the reference and score (decision 10); the text goes to the model."""

    id: str
    kind: str
    label: str
    score: float
    text: str
    topic_id: str | None = None
    used_tools: tuple[str, ...] = ()
    created_at: str = ""       # item 27: shown on retrieved tool memory
