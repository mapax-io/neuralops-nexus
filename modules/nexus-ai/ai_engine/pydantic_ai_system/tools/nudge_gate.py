"""
NudgeGate — W8 (Layer 4): what the caller adds while the reply runs.

Ported from 0.8.0 (NA/managers/nudges.py, read 2026-10-13): the persona takes
a nudge at its next step — after its next tool call — as part of that tool's
result ("The reader adds while you work: …"), which is the one place a running
agent reads new words. A run with no tool step never takes a nudge; nucleus
posts it as a message when the reply ends (never lost). One short GET per tool
call; a failed poll is no nudge.

One deliberate change from legacy (Layer 4 design point 2): there is no
side-channel stream merge — a taken nudge's event rides out with the NEXT
event flush (ReplyGenerator drains `pending_events` after each mapped batch),
a sub-second difference for much less machinery.
"""
from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from pydantic_ai.capabilities import AbstractCapability

from fastapi_app.contracts.trigger import AgentEvent, AgentEventType

log = logging.getLogger(__name__)

NUDGE_NOTE = "\n\n[The reader adds while you work: {text}]"


class NudgeGate(AbstractCapability):
    """After each tool call, hand the caller's nudges to the model with that
    call's result, and queue the nudge_taken events for the stream."""

    def __init__(self, msg_id: str, *, poll: Callable[[], Awaitable[list[str]]]):
        self.msg_id = msg_id
        self.poll = poll
        self.taken: list[str] = []
        self.pending_events: list[AgentEvent] = []

    def drain(self) -> list[AgentEvent]:
        out, self.pending_events = self.pending_events, []
        return out

    async def after_tool_execute(self, ctx, *, call, tool_def, args, result):
        try:
            texts = await self.poll()
        except Exception as exc:  # noqa: BLE001 — a hiccup is no nudge
            log.debug("[nudge] poll failed for %s: %s", self.msg_id, type(exc).__name__)
            return result
        if not texts:
            return result
        for text in texts:
            self.taken.append(text)
            self.pending_events.append(AgentEvent(
                type=AgentEventType.NUDGE_TAKEN, id=self.msg_id, nudge=text))
        note = "".join(NUDGE_NOTE.format(text=text.strip()) for text in texts)
        # A text result carries the note; anything else is rendered so the
        # model still sees it.
        return (result if isinstance(result, str) else str(result)) + note
