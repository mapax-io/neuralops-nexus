"""
Chat services — save/load messages + publish to Centrifugo + embed to nexus-ai.

Phase 1: human-to-human only.
Phase 2 extension: add @mention detection + nexus-ai trigger (additive, nothing here changes).
"""
from __future__ import annotations

import logging

import httpx
from django.conf import settings
from django.db.models import Max

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Centrifugo publish
# ---------------------------------------------------------------------------

def publish(channel: str, data: dict) -> None:
    """
    Synchronous publish — kept for compatibility with sync views.
    Prefer publish_async() inside async endpoints.
    """
    api_url = getattr(settings, "CENTRIFUGO_API_URL", "")
    api_key = getattr(settings, "CENTRIFUGO_API_KEY", "")
    if not api_url:
        logger.warning("[centrifugo] CENTRIFUGO_API_URL not set — skipping publish")
        return
    try:
        httpx.post(
            f"{api_url}/publish",
            json={"channel": channel, "data": data},
            headers={
                "X-API-Key": api_key,
                "Content-Type": "application/json",
            },
            timeout=3,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[centrifugo] publish failed channel=%s: %s", channel, exc)


async def publish_async(channel: str, data: dict) -> None:
    """
    Async publish — use inside async Django Ninja endpoints.
    Fire-and-forget via asyncio.create_task() so the response
    returns immediately without waiting for Centrifugo.
    """
    api_url = getattr(settings, "CENTRIFUGO_API_URL", "")
    api_key = getattr(settings, "CENTRIFUGO_API_KEY", "")
    if not api_url:
        logger.warning("[centrifugo] CENTRIFUGO_API_URL not set — skipping publish")
        return
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{api_url}/publish",
                json={"channel": channel, "data": data},
                headers={
                    "X-API-Key": api_key,
                    "Content-Type": "application/json",
                },
                timeout=3,
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[centrifugo] publish_async failed channel=%s: %s", channel, exc)


def topic_channel(topic_id: str) -> str:
    """Returns the Centrifugo channel name for a topic."""
    return f"topic-{topic_id}"


# ---------------------------------------------------------------------------
# Embed fire-and-forget (nexus-ai)
# ---------------------------------------------------------------------------

async def embed_message_async(
    *,
    message_id: str,
    company_id: str,
    sequence: int,
    topic_id: str,
    channel_id: str,
    project_id: str,
    sender_id: str,
    sender_name: str,
    sender_type: str,
    content: str,
    created_at: str,
) -> None:
    """
    Fire-and-forget: send message data to nexus-ai for embedding.

    nexus-ai embeds the content using FastEmbed and stores the vector
    in ChromaDB collection company_{company_id}_chat with full metadata.

    Skipped if NEXUS_AI_URL is not configured.
    Errors are logged and swallowed — embedding failure must never affect chat.
    """
    nexus_ai_url = getattr(settings, "NEXUS_AI_URL", "")
    internal_key = getattr(settings, "INTERNAL_API_KEY", "change-me-in-production")

    if not nexus_ai_url:
        logger.warning("[embed] NEXUS_AI_URL not set — skipping message embedding")
        return

    payload = {
        "message_id": message_id,
        "company_id": company_id,
        "sequence": sequence,
        "topic_id": topic_id,
        "channel_id": channel_id,
        "project_id": project_id,
        "sender_id": sender_id,
        "sender_name": sender_name,
        "sender_type": sender_type,
        "content": content,
        "created_at": created_at,
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{nexus_ai_url}/api/v1/embed/message/",
                json=payload,
                headers={
                    "X-Internal-Key": internal_key,
                    "Content-Type": "application/json",
                },
                timeout=15,
            )
            if response.status_code != 200:
                logger.warning(
                    "[embed] nexus-ai returned %s for message %s",
                    response.status_code, message_id,
                )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[embed] embed_message_async failed message=%s: %s", message_id, exc)


# ---------------------------------------------------------------------------
# AI trigger — fire-and-forget (M3)
# ---------------------------------------------------------------------------

def create_ai_message(company, project, topic, persona) -> dict:
    """Pre-create a PENDING ChatMessage for the AI response."""
    from nucleus.models import ChatMessage

    max_seq = (
        ChatMessage.objects.filter(topic_id=topic.id)
        .aggregate(Max("sequence"))["sequence__max"] or 0
    )

    msg = ChatMessage.objects.create(
        company=company,
        project=project,
        topic=topic,
        sender=persona.identity_user,
        content="",
        message_type=ChatMessage.MessageType.TEXT,
        status=ChatMessage.Status.PENDING,
        sequence=max_seq + 1,
        metadata={"role": "assistant", "persona_id": str(persona.id)},
    )
    return _serialise(msg)


def update_ai_message(message_id: str, content: str) -> None:
    """Update the AI message content and mark COMPLETED."""
    from nucleus.models import ChatMessage
    ChatMessage.objects.filter(id=message_id).update(
        content=content,
        status=ChatMessage.Status.COMPLETED,
    )


async def trigger_ai_response_async(
    *,
    company,
    project,
    topic,
    persona,
    user_message: str,
    history: list[dict],
    topic_id: str,
) -> None:
    """
    Fire-and-forget: trigger nexus-ai to generate a persona response.

    Flow:
        1. Pre-create AI message in DB (status=PENDING)
        2. Publish message_start to Centrifugo
        3. Call nexus-ai POST /api/v1/trigger/ — SSE stream
        4. For each message_delta: publish token to Centrifugo
        5. On message_done: update DB message (status=COMPLETED), publish message_done

    Errors are logged and swallowed — AI failure must never affect chat.
    """
    from asgiref.sync import sync_to_async
    import json
    import uuid
    from datetime import datetime, timezone

    nexus_ai_url = getattr(settings, "NEXUS_AI_URL", "")
    internal_key = getattr(settings, "INTERNAL_API_KEY", "")

    if not nexus_ai_url:
        logger.warning("[trigger] NEXUS_AI_URL not set — skipping AI response")
        return

    # 1. Pre-create AI message in DB
    _create_ai_message = sync_to_async(create_ai_message)
    _update_ai_message = sync_to_async(update_ai_message)

    try:
        ai_msg = await _create_ai_message(company, project, topic, persona)
    except Exception as exc:
        logger.warning("[trigger] failed to create AI message: %s", exc)
        return

    msg_id = ai_msg["id"]
    channel = topic_channel(topic_id)
    now = datetime.now(timezone.utc).isoformat()

    # 2. Publish message_start
    await publish_async(channel, {
        "type": "message_start",
        "id": msg_id,
        "sender_id": ai_msg["sender_id"],
        "sender_name": ai_msg["sender_name"],
        "sequence": ai_msg["sequence"],
        "created_at": now,
    })

    # 3. Build TriggerJob payload
    model = persona.model
    api_key = model.get_api_key() if model else None

    # Get system prompt — Prompt model uses system_prompt field
    system_prompt = ""
    if hasattr(persona, "prompt") and persona.prompt:
        system_prompt = persona.prompt.system_prompt or ""

    job_payload = {
        "job_id": str(uuid.uuid4()),
        "msg_id": msg_id,
        "persona": {
            "id": str(persona.id),
            "name": persona.name,
            "system_prompt": system_prompt,
            "model": {
                "provider": model.provider if model else "litellm",
                "model_id": model.model_id if model else getattr(settings, "LLM_MODEL", ""),
                "api_key": api_key,
                "max_tokens": model.max_tokens if model else 4096,
                "temperature": model.temperature if model else 0.7,
            },
        },
        "message": user_message,
        "history": history,
        "context_sources": _build_context_sources(topic, company),
    }

    # 4. Stream from nexus-ai, relay tokens to Centrifugo
    full_content: list[str] = []

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream(
                "POST",
                f"{nexus_ai_url}/api/v1/trigger/",
                json=job_payload,
                headers={
                    "X-Internal-Key": internal_key,
                    "Content-Type": "application/json",
                },
            ) as response:
                if response.status_code != 200:
                    body = await response.aread()
                    raise RuntimeError(
                        f"nexus-ai /trigger/ returned {response.status_code}: {body.decode()[:300]}"
                    )

                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    raw = line[6:].strip()
                    if not raw:
                        continue
                    try:
                        event = json.loads(raw)
                        event_type = event.get("type")

                        if event_type == "message_delta":
                            delta = event.get("delta") or ""
                            if delta:
                                full_content.append(delta)
                                await publish_async(channel, {
                                    "type": "message_delta",
                                    "id": msg_id,
                                    "delta": delta,
                                })

                        elif event_type == "message_done":
                            break

                    except (json.JSONDecodeError, KeyError):
                        continue

    except Exception as exc:
        logger.warning("[trigger] streaming error for msg %s: %s", msg_id, exc)

    # 5. Save full content to DB + publish message_done
    final_content = "".join(full_content)
    try:
        await _update_ai_message(msg_id, final_content)
    except Exception as exc:
        logger.warning("[trigger] failed to update AI message %s: %s", msg_id, exc)

    await publish_async(channel, {
        "type": "message_done",
        "id": msg_id,
        "content": final_content,
    })


# ---------------------------------------------------------------------------
# Read messages
# ---------------------------------------------------------------------------

def list_messages(topic_id: str, limit: int = 100) -> list[dict]:
    """Return the last *limit* messages in a topic, oldest first."""
    from nucleus.models import ChatMessage

    qs = (
        ChatMessage.objects.filter(topic_id=topic_id, is_active=True)
        .select_related("sender")
        .order_by("-created_at")[:limit]
    )
    return [_serialise(m) for m in reversed(list(qs))]


# ---------------------------------------------------------------------------
# Write messages
# ---------------------------------------------------------------------------

def save_system_message(company, project, topic, content: str) -> dict:
    """Save a system event message (no sender) and return its serialised form."""
    from nucleus.models import ChatMessage

    max_seq = (
        ChatMessage.objects.filter(topic_id=topic.id)
        .aggregate(Max("sequence"))["sequence__max"] or 0
    )

    msg = ChatMessage.objects.create(
        company=company,
        project=project,
        topic=topic,
        sender=None,
        content=content,
        message_type=ChatMessage.MessageType.SYSTEM,
        status=ChatMessage.Status.COMPLETED,
        sequence=max_seq + 1,
        metadata={"role": "system"},
    )
    return _serialise(msg)


def save_user_message(company, project, topic, user, content: str) -> dict:
    """Save a human message and return its serialised form."""
    from nucleus.models import ChatMessage

    # Auto-increment sequence within the topic
    max_seq = (
        ChatMessage.objects.filter(topic_id=topic.id)
        .aggregate(Max("sequence"))["sequence__max"] or 0
    )

    msg = ChatMessage.objects.create(
        company=company,
        project=project,
        topic=topic,
        sender=user,
        content=content,
        message_type=ChatMessage.MessageType.TEXT,
        status=ChatMessage.Status.COMPLETED,
        sequence=max_seq + 1,
        metadata={"role": "user"},
    )
    return _serialise(msg)


# ---------------------------------------------------------------------------
# Context sources for TriggerJob
# ---------------------------------------------------------------------------

def _build_context_sources(topic, company) -> list[dict]:
    """
    Build the context_sources list for TriggerJob.

    Always includes a ChatContext ref (semantic search over past messages).
    Plus any file/web sources attached to the topic that are ready.
    """
    sources = []

    # 1. ChatContext — always included so nexus-ai can search past messages
    sources.append({
        "source_id": str(topic.id),
        "type": "chat",
        "label": "Chat History",
        "collection_id": f"company_{company.id}_chat",
    })

    # 2. Attached file / web sources (only ready ones)
    from nucleus.models import ContextSource
    attached = ContextSource.objects.filter(
        topic_id=topic.id,
        is_active=True,
        status=ContextSource.Status.READY,
    )
    for src in attached:
        sources.append({
            "source_id": str(src.id),
            "type": "file",
            "label": src.name,
            "collection_id": src.collection_id,
        })

    return sources


# ---------------------------------------------------------------------------
# Serialiser
# ---------------------------------------------------------------------------

def _serialise(msg) -> dict:
    sender_name = (
        msg.sender.get_display_name()
        if msg.sender
        else None
    )
    return {
        "id": str(msg.id),
        "type": "message",
        "message_type": msg.message_type,
        "content": msg.content or "",
        "sender_name": sender_name,
        "sender_id": str(msg.sender_id) if msg.sender_id else None,
        "sender_type": getattr(msg.sender, "user_type", "human") if msg.sender else "system",
        "sequence": msg.sequence,
        "created_at": msg.created_at.isoformat(),
    }
