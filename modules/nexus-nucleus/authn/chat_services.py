"""
Chat services — save/load messages + publish to Centrifugo.

Phase 1: human-to-human only.
Phase 2 extension: add @mention detection + nexus-ai trigger (additive, nothing here changes).
"""
from __future__ import annotations

import logging

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Centrifugo publish
# ---------------------------------------------------------------------------

def publish(channel: str, data: dict) -> None:
    """
    Publish an event to a Centrifugo channel via HTTP API.
    Fire-and-forget — logs a warning on failure but never raises.

    Centrifugo event shapes:
        Human message  → { type: "message", id, content, sender_name, sender_id, created_at }
        AI token       → { type: "token",   message_id, content, sender_name }   (Phase 2)
        AI done        → { type: "done",    message_id, content, sender_name }   (Phase 2)
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


def topic_channel(topic_id: str) -> str:
    """Returns the Centrifugo channel name for a topic."""
    return f"topic:{topic_id}"


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

def save_user_message(company, project, topic, user, content: str) -> dict:
    """Save a human message and return its serialised form."""
    from nucleus.models import ChatMessage

    msg = ChatMessage.objects.create(
        company=company,
        project=project,
        topic=topic,
        sender=user,
        content=content,
        message_type=ChatMessage.MessageType.TEXT,
        status=ChatMessage.Status.COMPLETED,
        metadata={"role": "user"},
    )
    return _serialise(msg)


# ---------------------------------------------------------------------------
# Serialiser
# ---------------------------------------------------------------------------

def _serialise(msg) -> dict:
    sender_name = (
        getattr(msg.sender, "display_name", None)
        or getattr(msg.sender, "username", None)
        or getattr(msg.sender, "email", None)
        or str(msg.sender_id)
    )
    return {
        "id": str(msg.id),
        "type": "message",
        "content": msg.content or "",
        "sender_name": sender_name,
        "sender_id": str(msg.sender_id),
        "created_at": msg.created_at.isoformat(),
    }
