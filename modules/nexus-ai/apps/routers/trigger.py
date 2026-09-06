"""
POST /api/v1/trigger/
Called by nexus-nucleus when @mention is detected.
Returns an SSE stream of AgentEvents (message_start, message_delta, message_done).
nexus-nucleus consumes the stream and relays to Centrifugo + DB.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.security.api_key import APIKeyHeader

from apps.core.config import settings
from apps.factories.agent import AgentFactory
from apps.factories.embedding import EmbeddingFactory
from apps.factories.vectorstore import VectorStoreFactory
from apps.implementations.agents.litellm_runner import MCPReauthRequiredError
from apps.managers.agentic_manager import (
    AgenticManager,
    AgenticSwarmManager,
    NewImprovedAgenticManager,
)
from apps.schemas.trigger import (
    AgentEvent,
    TriggerJob,
    TriggerSwarmJob,
    AgentEventType,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["trigger"])

_api_key_header = APIKeyHeader(name="X-Internal-Key", auto_error=False)


def _verify_key(key: str = Depends(_api_key_header)):
    if key != settings.INTERNAL_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid internal API key")
    return key


async def _event_stream(job: TriggerJob):
    """
    Generate SSE events from the agentic pipeline.

    Wrapped in try/except -- without this, any failure anywhere in
    manager.run() (persona resolve, history fetch, the LLM call itself,
    ...) propagates straight out of this generator. StreamingResponse
    already sent its 200 headers by the time that happens, so the
    connection just dies mid-body instead of returning a clean error --
    nucleus sees "peer closed connection" with nothing useful to act on.
    Catching it here and yielding one message_error event instead means
    nucleus can mark the message FAILED with the real error text. See
    the #131 test-run incident this came from.
    """
    manager = NewImprovedAgenticManager(
        runner=AgentFactory.get(),
        embedder=EmbeddingFactory.get(),
        store=VectorStoreFactory.get(),
    )
    try:
        async for event in manager.run(job):
            yield f"data: {event.model_dump_json()}\n\n"
    except MCPReauthRequiredError as exc:
        yield f"data: {AgentEvent(type=AgentEventType.ERROR, id=job.msg_id, error=str(exc), error_code='mcp_reauth_required').model_dump_json()}\n\n"

    except Exception as exc:
        log.exception("[trigger] job %s failed: %s", job.job_id, exc)
        error_event = AgentEvent(
            type=AgentEventType.ERROR, id=job.msg_id, error=str(exc)
        )
        yield f"data: {error_event.model_dump_json()}\n\n"


async def _swarm_event_stream(job: TriggerSwarmJob):
    manager = AgenticSwarmManager(
        runner=AgentFactory.get(),
        embedder=EmbeddingFactory.get(),
        store=VectorStoreFactory.get(),
    )

    try:
        async for event in manager.run(job):
            yield f"data: {event.model_dump_json()}\n\n"
    except Exception as exc:
        log.exception("[trigger] job %s failed: %s", job.job_id, exc)
        error_event = AgentEvent(
            type=AgentEventType.ERROR, id=job.msg_id, error=str(exc)
        )
        yield f"data: {error_event.model_dump_json()}\n\n"


@router.post("/trigger/")
async def trigger(
    job: TriggerJob,
    _: str = Depends(_verify_key),
) -> StreamingResponse:
    """
    Receive an AI job from nexus-nucleus and stream AgentEvents back via SSE.
    nexus-nucleus consumes this stream to relay tokens to Centrifugo and save to DB.
    """
    return StreamingResponse(
        _event_stream(job),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable nginx buffering
        },
    )


@router.post("/trigger/swarm/")
async def swarm(
    job: TriggerSwarmJob,
    _: str = Depends(_verify_key),
) -> StreamingResponse:
    return StreamingResponse(
        _swarm_event_stream(job),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
