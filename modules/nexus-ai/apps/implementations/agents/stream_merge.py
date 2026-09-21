"""
One stream out of two: the agent's own events and the side events a
capability raises from inside a tool call (an approval request), plus a
keepalive whenever nothing has been said for a while.

Why: nucleus reads the worker's stream with an idle timeout of two minutes,
and a tool call that waits for a person -- or simply takes long -- says
nothing for longer than that. A keepalive is an event nucleus ignores by
type, so the connection stays warm at no cost to the reply.
"""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from apps.schemas.trigger import AgentEvent, AgentEventType


async def merge_events(stream: AsyncIterator[Any], side: asyncio.Queue, *, keepalive_seconds: float, msg_id: str = "") -> AsyncIterator[Any]:
    """Yield from `stream` and `side` as each has something; a keepalive after `keepalive_seconds` of silence."""
    source = stream.__aiter__()
    pending: asyncio.Future | None = None
    waiting: asyncio.Future | None = None
    try:
        while True:
            if pending is None:
                pending = asyncio.ensure_future(source.__anext__())
            if waiting is None:
                waiting = asyncio.ensure_future(side.get())
            done, _ = await asyncio.wait({pending, waiting}, timeout=keepalive_seconds, return_when=asyncio.FIRST_COMPLETED)
            if not done:
                yield AgentEvent(type=AgentEventType.KEEPALIVE, id=msg_id)
                continue
            if waiting in done:
                yield waiting.result()
                waiting = None
            if pending in done:
                try:
                    item = pending.result()
                except StopAsyncIteration:
                    # Anything a tool call queued at the very end still goes out.
                    while not side.empty():
                        yield side.get_nowait()
                    return
                pending = None
                yield item
    finally:
        for task in (pending, waiting):
            if task is not None and not task.done():
                task.cancel()
