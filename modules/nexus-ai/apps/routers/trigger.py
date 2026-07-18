"""
POST /api/v1/trigger/
Called by nexus-nucleus when @mention is detected.
Returns an SSE stream of AgentEvents (message_start, message_delta, message_done).
nexus-nucleus consumes the stream and relays to Centrifugo + DB.
"""
import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.security.api_key import APIKeyHeader

from apps.core.config import settings
from apps.schemas.trigger import TriggerJob
from apps.managers.agentic_manager import AgenticManager
from apps.factories.agent import AgentFactory
from apps.factories.embedding import EmbeddingFactory
from apps.factories.vectorstore import VectorStoreFactory

router = APIRouter(prefix="/api/v1", tags=["trigger"])

_api_key_header = APIKeyHeader(name="X-Internal-Key", auto_error=False)


def _verify_key(key: str = Depends(_api_key_header)):
    if key != settings.INTERNAL_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid internal API key")
    return key


async def _event_stream(job: TriggerJob):
    """Generate SSE events from the agentic pipeline."""
    manager = AgenticManager(
        runner=AgentFactory.get(),
        embedder=EmbeddingFactory.get(),
        store=VectorStoreFactory.get(),
    )
    async for event in manager.run(job):
        yield f"data: {event.model_dump_json()}\n\n"


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
            "X-Accel-Buffering": "no",     # disable nginx buffering
        },
    )
