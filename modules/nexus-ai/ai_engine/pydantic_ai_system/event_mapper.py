"""
EventMapper — pydantic-ai stream events → AgentEvent, text in small batches.

A batch goes out when it reaches batch_chars, or when batch_ms have passed
since the last send. map() is synchronous, so a time-based flush can only
happen when the NEXT event arrives — accepted: a sub-batch tail waits for
flush() at stream end, and EventStream's keepalive covers real silence.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

from pydantic_ai.messages import (
    DeferredToolRequestsEvent,
    PartDeltaEvent,
    PartStartEvent,
    TextPart,
    TextPartDelta,
)

from ai_engine.core.specs import PersonaSpec
from ai_engine.pydantic_ai_system.tools.approval_policy import args_preview
from fastapi_app.contracts.trigger import AgentEvent, AgentEventType, ApprovalRequestData


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

    def map(self, event: object) -> list[AgentEvent]:
        if isinstance(event, DeferredToolRequestsEvent):
            # Item 2: the run is about to pause — flush buffered text first so
            # event order on the wire mirrors what happened.
            out = self.flush()
            for call in event.requests.approvals:
                out.append(AgentEvent(
                    type=AgentEventType.APPROVAL_REQUESTED,
                    id=self._msg_id,
                    persona_id=self._persona.id,
                    persona_name=self._persona.name,
                    created_at=datetime.now(timezone.utc).isoformat(),
                    approval=ApprovalRequestData(
                        call_id=call.tool_call_id,
                        tool=call.tool_name,
                        capability_id=self._tool_capability_ids.get(call.tool_name, ""),
                        args_preview=args_preview(call.args),
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
