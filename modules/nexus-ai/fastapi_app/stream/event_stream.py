"""
EventStream — the stream guard. Three promises about every reply stream:

  1. a keepalive after `keepalive_seconds` of silence, so nucleus's read
     timeout never fires while the model thinks;
  2. never more than one final event (message_done, message_error or — item 2
     — message_paused), and exactly one whenever the client is still
     connected — a disconnected client gets nothing, there is no one to send to;
  3. an unexpected exception becomes one clean message_error, never a
     connection dropped mid-body.

It wraps whatever stream the AI system returns, so every AI system gets them.

The inner generator is pumped by a background task into a queue: waiting on
the queue with a timeout is how silence is noticed WITHOUT cancelling the
model call (asyncio.wait_for on the generator itself would cancel its await).
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import datetime, timezone
from typing import AsyncIterator

from fastapi_app.contracts.trigger import AgentEvent, AgentEventType, TriggerJob

log = logging.getLogger(__name__)

# Item 2: message_paused ends a stream as legitimately as done/error — without
# it here, the "ended without a final event" guard would add a bogus error.
_FINAL = (AgentEventType.END, AgentEventType.ERROR, AgentEventType.PAUSED)


class EventStream:
    def __init__(self, keepalive_seconds: float = 30.0) -> None:
        self.keepalive_seconds = keepalive_seconds

    async def wrap(self, events: AsyncIterator[AgentEvent], job: TriggerJob) -> AsyncIterator[bytes]:
        queue: asyncio.Queue = asyncio.Queue()

        async def pump() -> None:
            try:
                async for event in events:
                    await queue.put(("event", event))
            except asyncio.CancelledError:
                raise
            except BaseException as exc:  # noqa: BLE001 — becomes one message_error
                await queue.put(("error", exc))
            else:
                await queue.put(("end", None))

        task = asyncio.create_task(pump())
        final_sent = False
        try:
            while True:
                try:
                    kind, item = await asyncio.wait_for(queue.get(), self.keepalive_seconds)
                except (asyncio.TimeoutError, TimeoutError):
                    if not final_sent:
                        yield _sse(AgentEvent(
                            type=AgentEventType.KEEPALIVE, id=job.msg_id,
                            persona_id=job.persona_id, created_at=_now(),
                        ))
                    continue
                if kind == "end":
                    break
                if kind == "error":
                    log.exception("job %s failed", job.job_id, exc_info=item)
                    if not final_sent:
                        final_sent = True
                        yield _sse(_error_event(job, item))
                    break
                event: AgentEvent = item
                if event.type in _FINAL:
                    if final_sent:
                        continue  # never more than one final event
                    final_sent = True
                yield _sse(event)
            if not final_sent:
                # the AI system ended without done or error — still one final event
                final_sent = True
                yield _sse(_error_event(job, RuntimeError("the reply ended without a final event")))
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task  # lets the run's cleanup (usage recording) finish


def _sse(event: AgentEvent) -> bytes:
    return f"data: {event.model_dump_json()}\n\n".encode()


def _error_event(job: TriggerJob, exc: BaseException) -> AgentEvent:
    return AgentEvent(
        type=AgentEventType.ERROR, id=job.msg_id, persona_id=job.persona_id,
        created_at=_now(), error=str(exc) or type(exc).__name__,
    )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
