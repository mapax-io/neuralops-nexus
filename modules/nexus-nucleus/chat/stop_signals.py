"""
Stop signals for in-flight persona replies.

A reader clicks Stop on a streaming bubble; the relay in chat/services.py reads
the worker's stream through stoppable_lines(), which polls this on its own
clock and ends the run, keeping what streamed so far. Keyed by the AI message
id. Redis-backed so a stop raised on one nucleus worker reaches
the relay running on another; a memory store serves tests and single-process
use. Requests expire, so a stale click can never kill a later run.
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import AsyncIterator, Awaitable, Callable

from django.conf import settings

DEFAULT_TTL_SECONDS = 600
_NUDGE_KEY = "nx:nudge:{msg_id}"
NUDGE_TTL_SECONDS = 600
_KEY = "nx:stop:{msg_id}"
# How long a click waits, at most, before the relay sees it. One Redis EXISTS
# per tick per in-flight reply; imperceptible to the reader.
STOP_POLL_SECONDS = 0.15


class StopRequested(Exception):
    """Raised out of stoppable()/stoppable_lines() once the reader's stop is seen."""


async def _cancel(task: asyncio.Future) -> None:
    if not task.done():
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass


async def stoppable(awaitable, should_stop: Callable[[], Awaitable[bool]], poll_seconds: float = STOP_POLL_SECONDS):
    """
    Await one thing -- opening the worker's stream, which the worker precedes
    with its own setup -- while asking `should_stop` every `poll_seconds`.
    Raises StopRequested and cancels the awaitable.
    """
    task = asyncio.ensure_future(awaitable)
    try:
        while True:
            done, _ = await asyncio.wait({task}, timeout=poll_seconds)
            if done:
                return task.result()
            if await should_stop():
                raise StopRequested()
    finally:
        await _cancel(task)


async def stoppable_lines(
    lines: AsyncIterator[str],
    should_stop: Callable[[], Awaitable[bool]],
    poll_seconds: float = STOP_POLL_SECONDS,
) -> AsyncIterator[str]:
    """
    Yield `lines` as they arrive and ask `should_stop` every `poll_seconds` --
    on a timer, not per line, so a stop is seen while the worker is silent (a
    model thinking, a tool running), which is exactly when it used to wait for
    the next token. Raises StopRequested; the caller leaves the stream, which
    closes the connection and cancels the worker's run. Errors from the source
    propagate unchanged.
    """
    source = lines.__aiter__()
    pending: asyncio.Future | None = None
    last_check = time.monotonic()
    try:
        while True:
            if pending is None:
                pending = asyncio.ensure_future(source.__anext__())
            done, _ = await asyncio.wait({pending}, timeout=poll_seconds)
            now = time.monotonic()
            if now - last_check >= poll_seconds:
                last_check = now
                if await should_stop():
                    raise StopRequested()
            if not done:
                continue
            try:
                line = pending.result()
            except StopAsyncIteration:
                return
            pending = None
            yield line
    finally:
        if pending is not None:
            await _cancel(pending)


class MemoryStore:
    def __init__(self, now: Callable[[], float] = time.monotonic) -> None:
        self.now = now
        self._expiry: dict[str, float] = {}
        self._lists: dict[str, list[str]] = {}

    async def set(self, key: str, ttl: int) -> None:
        self._expiry[key] = self.now() + ttl

    async def exists(self, key: str) -> bool:
        expires = self._expiry.get(key)
        if expires is None:
            return False
        if self.now() > expires:
            del self._expiry[key]
            return False
        return True

    async def delete(self, key: str) -> None:
        self._expiry.pop(key, None)
        self._lists.pop(key, None)

    async def push(self, key: str, value: str, ttl: int) -> None:
        self._lists.setdefault(key, []).append(value)
        self._expiry[key] = self.now() + ttl

    async def pop_all(self, key: str) -> list[str]:
        if not await self.exists(key):
            self._lists.pop(key, None)
            return []
        return self._lists.pop(key, [])


class RedisStore:
    def __init__(self, url: str) -> None:
        import redis.asyncio as redis

        self._client = redis.from_url(url)

    async def set(self, key: str, ttl: int) -> None:
        await self._client.set(key, "1", ex=ttl)

    async def exists(self, key: str) -> bool:
        return bool(await self._client.exists(key))

    async def delete(self, key: str) -> None:
        await self._client.delete(key)

    async def push(self, key: str, value: str, ttl: int) -> None:
        async with self._client.pipeline() as pipe:
            pipe.rpush(key, value)
            pipe.expire(key, ttl)
            await pipe.execute()

    async def pop_all(self, key: str) -> list[str]:
        async with self._client.pipeline() as pipe:
            pipe.lrange(key, 0, -1)
            pipe.delete(key)
            values, _ = await pipe.execute()
        return [v.decode() if isinstance(v, bytes) else v for v in values or []]


class StopSignals:
    def __init__(self, store, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> None:
        self._store = store
        self._ttl = ttl_seconds

    async def request_stop(self, msg_id: str) -> None:
        await self._store.set(_KEY.format(msg_id=msg_id), self._ttl)

    async def is_stop_requested(self, msg_id: str) -> bool:
        return await self._store.exists(_KEY.format(msg_id=msg_id))

    async def clear(self, msg_id: str) -> None:
        await self._store.delete(_KEY.format(msg_id=msg_id))

    # ── Nudges (W8): what the caller adds while the reply runs ──────────────
    async def add_nudge(self, msg_id: str, nudge: dict) -> None:
        await self._store.push(_NUDGE_KEY.format(msg_id=msg_id), json.dumps(nudge), NUDGE_TTL_SECONDS)

    async def take_nudges(self, msg_id: str) -> list[dict]:
        """Every nudge waiting for this reply, in order -- and they wait no more."""
        out = []
        for raw in await self._store.pop_all(_NUDGE_KEY.format(msg_id=msg_id)):
            try:
                out.append(json.loads(raw))
            except ValueError:
                continue
        return out


_signals: StopSignals | None = None


def stop_signals() -> StopSignals:
    """The process-wide instance: Redis when the broker is configured, memory otherwise."""
    global _signals
    if _signals is None:
        url = getattr(settings, "CELERY_BROKER_URL", "")
        store = RedisStore(url) if url.startswith("redis") else MemoryStore()
        _signals = StopSignals(store)
    return _signals
