"""
Nudge (W8): what the caller adds while the reply runs. The persona takes it
at its next step -- after its next tool call -- as part of that tool's
result ("The reader adds while you work: …"), which is the one place a
running pydantic-ai agent reads new words. A run with no tool step never
takes a nudge; nucleus posts it as a message when the reply ends (never
lost). One short GET per tool call; a failed poll is no nudge.
"""
from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
from pydantic_ai.capabilities import AbstractCapability

from apps.core.config import settings
from apps.schemas.trigger import AgentEvent, AgentEventType

log = logging.getLogger(__name__)

NUDGE_NOTE = "\n\n[The reader adds while you work: {text}]"


def nucleus_nudges(msg_id: str) -> Callable[[], Awaitable[list[str]]]:
    """One GET of what waits for this reply on nucleus's internal API; the texts are taken once."""
    async def poll() -> list[str]:
        url = f"{settings.NEXUS_NUCLEUS_URL}/api/v1/internal/messages/{msg_id}/nudges/"
        async with httpx.AsyncClient(timeout=settings.NUDGE_POLL_TIMEOUT_SECONDS) as client:
            response = await client.get(url, headers={"X-Internal-API-Key": settings.INTERNAL_API_KEY})
            response.raise_for_status()
            return [t for t in (response.json().get("nudges") or []) if isinstance(t, str) and t.strip()]
    return poll


class NudgeGate(AbstractCapability):
    """After each tool call, hand the caller's nudges to the model with that call's result, and say so on the stream."""

    def __init__(self, msg_id: str, *, poll: Callable[[], Awaitable[list[str]]], emit: Callable[[AgentEvent], Any]):
        self.msg_id = msg_id
        self.poll = poll
        self.emit = emit
        self.taken: list[str] = []

    async def after_tool_execute(self, ctx, *, call, tool_def, args, result):
        try:
            texts = await self.poll()
        except Exception as exc:  # noqa: BLE001 -- a hiccup is no nudge
            log.debug("[nudge] poll failed for %s: %s", self.msg_id, type(exc).__name__)
            return result
        if not texts:
            return result
        for text in texts:
            self.taken.append(text)
            self.emit(AgentEvent(type=AgentEventType.NUDGE_TAKEN, id=self.msg_id, nudge=text))
        note = "".join(NUDGE_NOTE.format(text=text.strip()) for text in texts)
        # A text result carries the note; anything else is rendered so the model still sees it.
        return (result if isinstance(result, str) else str(result)) + note
