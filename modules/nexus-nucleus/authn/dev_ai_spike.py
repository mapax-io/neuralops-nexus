"""
⚠️  TEMPORARY SPIKE — DELETE when nexus-ai streaming is wired up.

Purpose
-------
Validates the full streaming pipeline end-to-end without building nexus-ai yet:

  /ai-test <message>
      → POST /api/v1/dev/{project_id}/channels/{channel_id}/topics/{topic_id}/ai-stream/
      → OpenAI GPT-4o streams tokens via httpx SSE (no openai package needed)
      → Each token published to Centrifugo as message_delta
      → React accumulates deltas in real time

Centrifugo event format (same format nexus-ai will use permanently):
    { "type": "message_start", "id": "<uuid>", "sender_id": "ai",
      "sender_name": "NeuralOps AI", "created_at": "<iso>" }
    { "type": "message_delta", "id": "<uuid>", "delta": "<token>" }
    { "type": "message_done",  "id": "<uuid>" }

Cleanup checklist (when nexus-ai is ready):
    1. Delete this file
    2. Remove `api.add_router("/dev/", dev_spike_router)` from authn/urls.py
    3. Remove the `/ai-test` branch from useChat.ts send()
    4. Remove triggerAiSpike() from chat.service.ts
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime, timezone

import httpx
from asgiref.sync import sync_to_async
from ninja import Router
from ninja.errors import HttpError

from .auth import SupabaseBearer
from .chat_services import publish_async, topic_channel
from . import workspace_services as ws_svc

logger = logging.getLogger(__name__)

router = Router(tags=["⚠️ DEV-SPIKE — delete me"], auth=SupabaseBearer())


# ---------------------------------------------------------------------------
# OpenAI streaming via raw httpx SSE — no openai package required
# ---------------------------------------------------------------------------

async def _stream_claude_to_centrifugo(
    channel: str,
    msg_id: str,
    user_message: str,
) -> None:
    """
    Stream Claude Haiku tokens and publish each one as a message_delta.
    Uses Anthropic's SSE streaming API directly via httpx — no SDK needed.
    Runs as a fire-and-forget asyncio task.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        await publish_async(channel, {
            "type": "message_delta",
            "id": msg_id,
            "delta": "⚠️  `ANTHROPIC_API_KEY` is not set in the environment.",
        })
        await publish_async(channel, {"type": "message_done", "id": msg_id})
        return

    full_content: list[str] = []

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            async with client.stream(
                "POST",
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-haiku-4-5-20251001",
                    "max_tokens": 1024,
                    "stream": True,
                    "system": (
                        "You are NeuralOps AI, a helpful assistant embedded "
                        "in the NeuralOps platform. Be clear and concise."
                    ),
                    "messages": [
                        {"role": "user", "content": user_message},
                    ],
                },
            ) as response:
                if response.status_code != 200:
                    body = await response.aread()
                    raise RuntimeError(
                        f"Anthropic returned HTTP {response.status_code}: {body.decode()[:300]}"
                    )

                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    payload = line[6:].strip()
                    if not payload:
                        continue
                    try:
                        event_data = json.loads(payload)
                        # Anthropic streams content_block_delta events with text_delta
                        if event_data.get("type") == "content_block_delta":
                            delta_text = (
                                event_data.get("delta", {})
                                .get("text") or ""
                            )
                            if delta_text:
                                full_content.append(delta_text)
                                await publish_async(channel, {
                                    "type": "message_delta",
                                    "id": msg_id,
                                    "delta": delta_text,
                                })
                    except (json.JSONDecodeError, KeyError):
                        continue

    except Exception as exc:  # noqa: BLE001
        logger.warning("[dev_ai_spike] streaming error: %s", exc)
        err_text = f"\n\n⚠️  Streaming error: {exc}"
        full_content.append(err_text)
        await publish_async(channel, {
            "type": "message_delta",
            "id": msg_id,
            "delta": err_text,
        })

    # Signal completion
    await publish_async(channel, {"type": "message_done", "id": msg_id})


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

_get_company = sync_to_async(ws_svc.get_company)
_get_project = sync_to_async(ws_svc.get_project)


@router.post(
    "/{project_id}/channels/{channel_id}/topics/{topic_id}/ai-stream/",
    response={200: dict},
)
async def ai_stream_spike(
    request,
    project_id: str,
    channel_id: str,
    topic_id: str,
):
    """
    ⚠️  TEMPORARY — validates Centrifugo streaming pipeline only.

    Body: { "content": "<user message>" }
    Returns immediately; GPT-4o tokens flow via Centrifugo WebSocket.
    """
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        raise HttpError(400, "Invalid JSON body")

    user_message = (body.get("content") or "").strip()
    if not user_message:
        raise HttpError(400, "content is required")

    # Verify user has access to this project
    user = request.auth
    company = await _get_company()
    if not company:
        raise HttpError(503, "Server not initialised.")

    project = await _get_project(company, user, project_id)
    if not project:
        raise HttpError(404, "Project not found.")

    # Generate a temporary AI message ID and announce the stream start
    msg_id = str(uuid.uuid4())
    channel = topic_channel(topic_id)
    now = datetime.now(timezone.utc).isoformat()

    await publish_async(channel, {
        "type": "message_start",
        "id": msg_id,
        "sender_id": "ai",
        "sender_name": "NeuralOps AI",
        "created_at": now,
    })

    # Kick off streaming in the background — return HTTP 200 immediately
    asyncio.create_task(
        _stream_claude_to_centrifugo(channel, msg_id, user_message)
    )

    return {"ok": True, "message_id": msg_id}
