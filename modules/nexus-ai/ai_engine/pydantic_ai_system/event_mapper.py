"""
EventMapper — pydantic-ai stream events → AgentEvent, text in small batches.

A batch goes out when it reaches batch_chars, or when batch_ms have passed
since the last send. map() is synchronous, so a time-based flush can only
happen when the NEXT event arrives — accepted: a sub-batch tail waits for
flush() at stream end, and EventStream's keepalive covers real silence.

Item 19 (activity trail, 0.8.0 shapes kept): FunctionToolCallEvent →
tool_call_start; FunctionToolResultEvent → tool_call_end with outcome,
duration and a clipped preview. A call resumed in a fresh process has no
recorded start there — its duration counts from the resume, which is also the
honest number (the wait belonged to a person, not the tool).
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote_plus

from pydantic_ai.messages import (
    DeferredToolRequestsEvent,
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    PartDeltaEvent,
    PartStartEvent,
    RetryPromptPart,
    TextPart,
    TextPartDelta,
    ToolReturnPart,
)

from ai_engine.core.specs import PersonaSpec
from ai_engine.pydantic_ai_system.tools.approval_policy import args_preview
from fastapi_app.contracts.trigger import (
    AgentEvent,
    AgentEventType,
    ApprovalRequestData,
    QuestionData,
    ToolCallData,
    ToolResultData,
)

TOOL_PREVIEW_CHARS = 600
TOOL_ERROR_CHARS = 300


def _args_dict(args: Any) -> dict:
    """ToolCallPart.args is a JSON string (or already a dict); the event wants a dict."""
    if isinstance(args, dict):
        return args
    if isinstance(args, str):
        try:
            parsed = json.loads(args)
            return parsed if isinstance(parsed, dict) else {}
        except ValueError:
            return {}
    return {}


def preview_of(content: Any) -> str | None:
    if content is None:
        return None
    text = content if isinstance(content, str) else str(content)
    return text[:TOOL_PREVIEW_CHARS]


def url_of(name: str, args: dict | None) -> str | None:
    """The page a web tool call is about: web_fetch's url, or a results page
    for a search query. None otherwise. (0.8.0's rule, kept.)"""
    args = args or {}
    url = args.get("url")
    if isinstance(url, str) and url.startswith(("http://", "https://")):
        return url
    if name in {"web_search", "duckduckgo_search", "search"}:
        query = args.get("query") or args.get("q")
        if isinstance(query, str) and query.strip():
            return "https://www.bing.com/search?q=" + quote_plus(query.strip())
    return None


class EventMapper:
    def __init__(self, msg_id: str, persona: PersonaSpec,
                 batch_chars: int = 40, batch_ms: int = 50,
                 tool_capability_ids: dict[str, str] | None = None) -> None:
        self._msg_id = msg_id
        self._persona = persona
        self._batch_chars = batch_chars
        self._batch_ms = batch_ms
        # live reference to ApprovalGate.tool_capability_ids (filled before any
        # model call) — labels approval cards with the tool's source
        self._tool_capability_ids = tool_capability_ids if tool_capability_ids is not None else {}
        self._buffer = ""
        self._received: list[str] = []
        self._last_sent = time.monotonic()
        self._tool_started: dict[str, tuple[str, dict, float]] = {}  # call_id → (name, args, t0)
        # tools that actually EXECUTED (ok tool_call_end) — goes out on
        # message_done.used_tools and later into vector metadata (item 44)
        self.used_tools: list[str] = []
        # item 27 (Layer 4): the run's FULL tool outputs for the memory pass —
        # capped per output so one giant dump can't blow the pass's prompt.
        self.tool_outputs: list[dict] = []

    def map(self, event: object) -> list[AgentEvent]:
        if isinstance(event, FunctionToolCallEvent):
            # Item 19: a persona reached for a tool. Flush text first so the
            # wire order mirrors what happened.
            name = event.part.tool_name
            args = _args_dict(event.part.args)
            self._tool_started[event.part.tool_call_id] = (name, args, time.monotonic())
            return self.flush() + [self._event(
                AgentEventType.TOOL_CALL_START,
                tool_call=ToolCallData(name=name, args=args),
            )]
        if isinstance(event, FunctionToolResultEvent):
            # Item 19: how it went. A RetryPromptPart is a failed call.
            part = event.part
            call_id = getattr(part, "tool_call_id", "")
            name, args, started = self._tool_started.pop(
                call_id, (getattr(part, "tool_name", None) or "tool", {}, time.monotonic()),
            )
            ok = isinstance(part, ToolReturnPart) and not isinstance(part, RetryPromptPart)
            if ok and name not in self.used_tools:
                self.used_tools.append(name)
            content = getattr(part, "content", None)
            if ok and content is not None:
                self.tool_outputs.append({
                    "tool": name, "args": args,
                    "content": (content if isinstance(content, str) else str(content))[:20_000],
                })
            return self.flush() + [self._event(
                AgentEventType.TOOL_CALL_END,
                tool_result=ToolResultData(
                    name=name,
                    ok=ok,
                    duration_ms=max(0, int((time.monotonic() - started) * 1000)),
                    preview=preview_of(content) if ok else None,
                    error=(preview_of(content) or "")[:TOOL_ERROR_CHARS] or None if not ok else None,
                    url=url_of(name, args),
                ),
            )]
        if isinstance(event, DeferredToolRequestsEvent):
            # Item 2: the run is about to pause — flush buffered text first so
            # event order on the wire mirrors what happened.
            out = self.flush()
            for call in event.requests.approvals:
                out.append(self._event(
                    AgentEventType.APPROVAL_REQUESTED,
                    approval=ApprovalRequestData(
                        call_id=call.tool_call_id,
                        tool=call.tool_name,
                        capability_id=self._tool_capability_ids.get(call.tool_name, ""),
                        args_preview=args_preview(call.args),
                    ),
                ))
            # Item 5: an ask_user call is a QUESTION for the person — the card
            # posts the answer back through the resume.
            for call in event.requests.calls:
                args = _args_dict(call.args)
                out.append(self._event(
                    AgentEventType.QUESTION,
                    question=QuestionData(
                        call_id=call.tool_call_id,
                        question=str(args.get("question", "")),
                        options=[str(o) for o in (args.get("options") or [])],
                    ),
                ))
            return out
        text = ""
        if isinstance(event, PartStartEvent) and isinstance(event.part, TextPart):
            text = event.part.content
        elif isinstance(event, PartDeltaEvent) and isinstance(event.delta, TextPartDelta):
            text = event.delta.content_delta
        if not text:
            return []
        self._received.append(text)
        self._buffer += text
        due = (time.monotonic() - self._last_sent) * 1000 >= self._batch_ms
        if len(self._buffer) >= self._batch_chars or due:
            return self.flush()
        return []

    def flush(self) -> list[AgentEvent]:
        if not self._buffer:
            return []
        delta, self._buffer = self._buffer, ""
        self._last_sent = time.monotonic()
        return [AgentEvent(
            type=AgentEventType.DELTA,
            id=self._msg_id,
            persona_id=self._persona.id,
            persona_name=self._persona.name,
            created_at=datetime.now(timezone.utc).isoformat(),
            delta=delta,
        )]

    def text(self) -> str:
        """Everything received from the model so far (sent or still buffered)."""
        return "".join(self._received)

    def _event(self, type_: AgentEventType, **fields) -> AgentEvent:
        return AgentEvent(
            type=type_,
            id=self._msg_id,
            persona_id=self._persona.id,
            persona_name=self._persona.name,
            created_at=datetime.now(timezone.utc).isoformat(),
            **fields,
        )
