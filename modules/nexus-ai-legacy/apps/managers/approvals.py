"""
Tool approvals: per persona, each tool carries a level Auto / Ask / Off.

Nucleus stores the persona's levels (`tool_levels`, a {key: level} map keyed
by capability id -- "shell", "filesystem", "web_search", "web_fetch",
"mcp:<server id>" -- or by "<capability>/<tool>" for one tool); the WORKER
owns the defaults, as it owns preflight's "would this run act" judgement:
reading is automatic, acting asks, an MCP tool asks unless its annotations
say it is read-only. Off hides the tool from the model altogether.

An Ask tool holds until a person in the topic decides. Nucleus is the source
of truth for the decision (it lands on the reply row under
persona.approve_run); the worker announces the request on its event stream
and polls nucleus for the answer while the run stays open, the way a Stop
reaches the relay. A denial, a timeout or a stop skips the call with a
one-line reason the model sees, so it can explain or try another way.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

import httpx
from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.exceptions import SkipToolExecution

from apps.core.config import settings
from apps.schemas.trigger import AgentEvent, AgentEventType, ApprovalRequestData

log = logging.getLogger(__name__)

LEVELS = ("auto", "ask", "off")

# Built-in tools that change something outside the conversation. Everything
# else a built-in capability offers only reads.
ACTING_TOOLS = {
    "shell": {"run_command", "start_command"},
    "filesystem": {"write_file", "edit_file", "create_directory"},
}
MCP_PREFIX = "mcp:"
PREVIEW_CHARS = 300


def level_for(levels: Mapping[str, str], capability_id: str | None, tool_name: str, metadata: Mapping[str, Any] | None = None) -> str:
    """The level one tool runs at: its own key, then its capability's, then the default."""
    cap = capability_id or ""
    for key in (f"{cap}/{tool_name}", cap):
        level = levels.get(key)
        if level in LEVELS:
            return level
    if cap.startswith(MCP_PREFIX):
        annotations = (metadata or {}).get("annotations") or {}
        return "auto" if annotations.get("readOnlyHint") is True else "ask"
    return "ask" if tool_name in ACTING_TOOLS.get(cap, ()) else "auto"


def args_preview(args: Mapping[str, Any]) -> str:
    """One short line of what the call would do -- for the approval row, never the raw object."""
    text = ", ".join(f"{k}: {json.dumps(v, ensure_ascii=False, default=str)}" for k, v in args.items())
    return text if len(text) <= PREVIEW_CHARS else text[: PREVIEW_CHARS - 1] + "…"


@dataclass(frozen=True)
class ApprovalRequest:
    call_id: str
    tool: str
    capability_id: str
    args_preview: str


@dataclass(frozen=True)
class ApprovalOutcome:
    decision: str  # allow | deny | timeout | stopped
    always: bool = False


Asker = Callable[[ApprovalRequest], Awaitable[ApprovalOutcome]]

REFUSED_UNATTENDED = "{tool} needs a person's approval, and nobody can give one in this run (a schedule or a swarm). Say what you would have done instead."
# Each reason states that the call did NOT run: told only "declined", a model
# has answered with invented output as if it had.
DENIED = "The person declined this call. It did not run and nothing changed. Say so plainly and do not show any output for it; explain, or find another way."
TIMED_OUT = "Nobody decided on {tool} in time. It did not run and nothing changed. Say so plainly and do not show any output for it."
STOPPED = "The reply was stopped before {tool} could be approved. It did not run."


@dataclass
class ToolApprovalGate(AbstractCapability):
    """
    The capability that applies a persona's levels: Off tools never reach the
    model, Ask tools wait on `ask` (nucleus, in production; anything awaitable
    in tests). "Always allow" clears that one tool for the rest of the run.
    """
    levels: Mapping[str, str] = field(default_factory=dict)
    ask: Asker | None = None
    interactive: bool = True
    cleared: set[str] = field(default_factory=set)
    # Seconds each call spent waiting for a person, by call id -- the runner
    # takes it off the call's duration, so the trail times the tool, not the wait.
    waits: dict[str, float] = field(default_factory=dict)

    async def prepare_tools(self, ctx, tool_defs):
        return [t for t in tool_defs if level_for(self.levels, t.capability_id, t.name, t.metadata) != "off"]

    async def before_tool_execute(self, ctx, *, call, tool_def, args):
        if getattr(ctx, "tool_call_approved", False):
            return args
        cap = tool_def.capability_id or ""
        key = f"{cap}/{call.tool_name}"
        if level_for(self.levels, cap, call.tool_name, tool_def.metadata) != "ask" or key in self.cleared:
            return args
        if not self.interactive or self.ask is None:
            raise SkipToolExecution(REFUSED_UNATTENDED.format(tool=call.tool_name))
        started = time.monotonic()
        try:
            outcome = await self.ask(ApprovalRequest(call_id=call.tool_call_id, tool=call.tool_name, capability_id=cap, args_preview=args_preview(args)))
        finally:
            self.waits[call.tool_call_id] = time.monotonic() - started
        if outcome.decision == "allow":
            if outcome.always:
                self.cleared.add(key)
            return args
        if outcome.decision == "deny":
            raise SkipToolExecution(DENIED)
        if outcome.decision == "stopped":
            raise SkipToolExecution(STOPPED.format(tool=call.tool_name))
        raise SkipToolExecution(TIMED_OUT.format(tool=call.tool_name))


# What nucleus's poll endpoint says a pending approval has become.
_OUTCOMES = {"allowed": "allow", "denied": "deny", "stopped": "stopped"}


class NucleusApprovals:
    """
    The asker for a live run: announce the request on the event stream (the
    relay stores it and tells the topic), then poll nucleus until someone
    decides, the reply is stopped, or the timeout passes. A poll that fails
    is a hiccup, not a decision.
    """

    def __init__(self, msg_id: str, *, poll: Callable[[str], Awaitable[dict]], emit: Callable[[AgentEvent], Any],
                 poll_seconds: float | None = None, timeout_seconds: float | None = None):
        self.msg_id = msg_id
        self.poll = poll
        self.emit = emit
        self.poll_seconds = settings.APPROVAL_POLL_SECONDS if poll_seconds is None else poll_seconds
        self.timeout_seconds = settings.APPROVAL_TIMEOUT_SECONDS if timeout_seconds is None else timeout_seconds

    async def __call__(self, request: ApprovalRequest) -> ApprovalOutcome:
        self.emit(AgentEvent(
            type=AgentEventType.APPROVAL_REQUESTED, id=self.msg_id,
            approval=ApprovalRequestData(call_id=request.call_id, tool=request.tool, capability_id=request.capability_id, args_preview=request.args_preview),
        ))
        deadline = time.monotonic() + self.timeout_seconds
        while True:
            try:
                answer = await self.poll(request.call_id)
            except Exception as exc:
                log.warning("[approvals] poll failed for %s/%s: %s", self.msg_id, request.call_id, exc)
                answer = {}
            decision = _OUTCOMES.get(answer.get("status") or "")
            if decision:
                return ApprovalOutcome(decision, always=bool(answer.get("always")))
            if time.monotonic() >= deadline:
                return ApprovalOutcome("timeout")
            await asyncio.sleep(self.poll_seconds)


def nucleus_poll(msg_id: str) -> Callable[[str], Awaitable[dict]]:
    """One GET of the approval's state on nucleus's internal API."""
    async def poll(call_id: str) -> dict:
        url = f"{settings.NEXUS_NUCLEUS_URL}/api/v1/internal/messages/{msg_id}/approvals/{call_id}/"
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, headers={"X-Internal-API-Key": settings.INTERNAL_API_KEY})
            response.raise_for_status()
            return response.json()
    return poll
