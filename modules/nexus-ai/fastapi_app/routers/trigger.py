"""
POST /api/v1/trigger/ — the core (Layer 0).

The router stays thin: check the internal key, ask AISystemFactory for the AI
system, return the guarded stream. One call into the AI system; the steps of a
reply live in PydanticAISystem (dependency rule 5).

Auth: X-Internal-Key (O5). The 0.8.0 nucleus already sends this name in this
direction, so no nucleus change is needed for inbound auth.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.security.api_key import APIKeyHeader

from ai_engine.core.ai_system import AISystemFactory
from ai_engine.core.config import EngineSettings
from fastapi_app.contracts.trigger import TriggerJob
from fastapi_app.stream.event_stream import EventStream

router = APIRouter(prefix="/api/v1", tags=["trigger"])

_api_key_header = APIKeyHeader(name="X-Internal-Key", auto_error=False)


def _verify_key(key: str = Depends(_api_key_header)) -> str:
    if key != EngineSettings().internal_key:
        raise HTTPException(status_code=401, detail="Invalid internal API key")
    return key


@router.post("/trigger/")
async def trigger(job: TriggerJob, _: str = Depends(_verify_key)) -> StreamingResponse:
    system = AISystemFactory.create("pydantic_ai")
    stream = EventStream(keepalive_seconds=EngineSettings().keepalive_seconds)
    return StreamingResponse(
        stream.wrap(system.respond(job), job),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable nginx buffering
        },
    )
