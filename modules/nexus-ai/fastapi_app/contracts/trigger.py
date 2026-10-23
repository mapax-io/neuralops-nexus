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


class ApprovalDecisionIn(BaseModel):
    """One decision inside a resume (item 2). Nucleus enforced WHO decided
    (persona.approve_run at the topic, approval_scope); nexus-ai only applies it."""

    decision: str  # "allow" | "deny"
    reason: str | None = None  # deny only; defaults to the standard denial text


class ResumeBlock(BaseModel):
    """Resume a paused run (item 2 / item 27): the pause state nucleus stored
    (exactly what nexus-ai POSTed at pause time) plus the decisions, keyed by
    tool_call_id. Travels on the SAME trigger endpoint; the rest of the job's
    fields are the original trigger's, resent."""

    state: str  # ModelMessages JSON, verbatim from the pause POST
    approvals: dict[str, ApprovalDecisionIn] = Field(default_factory=dict)
    # Item 5: the person's answers to ask_user questions, keyed by
    # tool_call_id — each becomes that call's TOOL RESULT on the resume.
    answers: dict[str, str] = Field(default_factory=dict)
    # Item 13: which model ROLE was running when the run paused (from the
    # pause POST) — the resume rebuilds the agent on the same seat, so a
    # DEEP-paused run never resumes on the STANDARD model.
    role: str = "STANDARD"


class ContextSourceRef(BaseModel):
    """One attached context source, pushed by nucleus inside the job (0.8.0 shape)."""

    source_id: str
    type: str  # "doc" | "code" | "chat" | "file" ("recall" left with the Recall feature, 2026-10-22)
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

    # Item 1 (nucleus change 8): the topic's stored loaded tool set. None from
    # today's nucleus → the first-reply rule applies (all eligible, capped).
    topic_tools: list[str] | None = None

    # Item 2 (nucleus change 8, extended): catalog tool_ids the topic cleared
    # as reads ("always allow" on an unlabeled MCP tool — decision 6).
    topic_tool_clearances: list[str] | None = None

    # Item 2: present only on a resume of a paused run.
    resume: ResumeBlock | None = None

    # Accepted and ignored in Layer 0 — kept so the 0.8.0 payload validates.
    # Layer 4 made interactive live (ask/nudge gating); Layer 6 made preflight,
    # approved_plan and step_context live (turn_rules). routine_id and
    # context_sources stay accepted-and-ignored (routines are nucleus-side).
    context_sources: list[ContextSourceRef] = Field(default_factory=list)
    output_type: str = "auto"
    preflight: bool = False
    approved_plan: str | None = None
    interactive: bool = True
    routine_id: str | None = None
    step_context: str | None = None

    # Item 46 (Layer 6): set to 1 on the inner job of a call_persona run —
    # the depth limit; a called persona never gets the delegation tool.
    delegation_depth: int = 0


class AgentEventType(str, Enum):
    START = "message_start"
    DELTA = "message_delta"
    END = "message_done"
    ERROR = "message_error"
    KEEPALIVE = "keepalive"
    # Item 2: the 0.8.0 names nucleus's relay already knows, kept
    APPROVAL_REQUESTED = "approval_requested"
    PAUSED = "message_paused"  # the final event of a paused run — no message_done
    # Item 19: the activity trail — 0.8.0's names and shapes, kept
    TOOL_CALL_START = "tool_call_start"
    TOOL_CALL_END = "tool_call_end"
    # Item 13/46: the router handed over — the deeper model is taking the reply
    ESCALATION = "deep_escalation"
    # Layer 3 decision 10: the reply pulled project memory — references only
    CONTEXT_RETRIEVED = "context_retrieved"
    # Item 5 (Layer 4): the model asked the person something — the run pauses
    QUESTION = "question_asked"
    # Nudges / W8 (Layer 4): the caller's mid-run note reached the model
    NUDGE_TAKEN = "nudge_taken"


class RetrievedRef(BaseModel):
    """One retrieved memory, as the UI sees it (Layer 3 decision 10): the
    reference and score only — the chunk text itself never rides an event."""

    id: str
    kind: str                  # "message" | "context_source" | "tool_result"
    label: str
    score: float
    topic_id: str | None = None


class QuestionData(BaseModel):
    """question_asked (item 5): what the model wants to know. The card posts
    the answer back through the resume (ResumeBlock.answers[call_id])."""

    call_id: str
    question: str
    options: list[str] = Field(default_factory=list)


class ToolCallData(BaseModel):
    """tool_call_start: a persona reached for a tool (0.8.0 shape)."""

    name: str
    args: dict = Field(default_factory=dict)


class ToolResultData(BaseModel):
    """tool_call_end: how it went (0.8.0 shape) — name, outcome, duration and a
    clipped text preview, never the raw object."""

    name: str
    ok: bool
    duration_ms: int
    preview: str | None = None  # the result's text, clipped
    error: str | None = None    # short reason when ok is False
    # The page a web tool went to (web_fetch's url; a search's results page),
    # so the app can open it beside the chat.
    url: str | None = None


class ApprovalRequestData(BaseModel):
    """What the approval card shows — 0.8.0's exact shape (ApprovalRequestData
    in nexus-ai-legacy/apps/schemas/trigger.py): a 300-char args preview, never
    the raw object. The full args live inside the pause state (decision 7)."""

    call_id: str
    tool: str
    capability_id: str
    args_preview: str


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

    # approval_requested only (item 2)
    approval: ApprovalRequestData | None = None

    # question_asked only (item 5)
    question: QuestionData | None = None

    # nudge_taken only (W8): the text the model just received mid-run
    nudge: str | None = None

    # tool_call_start / tool_call_end only (item 19)
    tool_call: ToolCallData | None = None
    tool_result: ToolResultData | None = None

    # deep_escalation only (items 13/46): the model now answering
    escalated_to: str | None = None

    # message_done / message_paused (items 13 + Layer 3 bridge):
    # loaded_tools — the tool set this reply ran with; on a topic's FIRST
    #   reply nucleus stores it as topic_tools (change 8). None when no
    #   tool-bearing run happened (e.g. the router answered from knowledge) —
    #   the topic's set then stays undecided, deliberately.
    # used_tools — the tools that actually EXECUTED in this reply (from the
    #   activity trail); stored on the message row, later carried as vector
    #   metadata (item 44) so retrieval returns "text + what solved it".
    loaded_tools: list[str] | None = None
    used_tools: list[str] | None = None

    # context_retrieved only (Layer 3 decision 10): what the search attached —
    # emitted ONLY when something cleared the threshold, references and scores
    # only. message_done carries the same list as retrieved_sources, which
    # nucleus stores on the message row beside used_tools (change 8 pattern).
    retrieved: list[RetrievedRef] | None = None
    count: int | None = None
    # message_done only (decision 10, second half)
    retrieved_sources: list[RetrievedRef] | None = None

    # message_done only (item 23, Layer 4): the <<<EMBED>>>/<<<CONTEXT>>>
    # narrative for a RENDERED reply — what nucleus should embed for item 44
    # instead of raw HTML/JSON. None for plain text replies.
    embed_description: str | None = None
