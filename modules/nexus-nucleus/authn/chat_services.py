"""
Chat services — save/load messages, build conversation history.
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


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
    messages = list(reversed(list(qs)))
    return [_serialise(m) for m in messages]


# ---------------------------------------------------------------------------
# Write messages
# ---------------------------------------------------------------------------

def save_user_message(
    company,
    project,
    topic,
    user,
    content: str,
) -> dict:
    """Persist the user's message and return its serialised form."""
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


def create_ai_placeholder(company, project, topic) -> "ChatMessage":
    """Create a PENDING AI message that the Celery task will fill in."""
    from nucleus.models import ChatMessage

    msg = ChatMessage.objects.create(
        company=company,
        project=project,
        topic=topic,
        sender=None,          # AI — no user sender
        content="",
        message_type=ChatMessage.MessageType.TEXT,
        status=ChatMessage.Status.PENDING,
        metadata={"role": "assistant"},
    )
    return msg


# ---------------------------------------------------------------------------
# Conversation history helper (for AI context)
# ---------------------------------------------------------------------------

def build_history(topic_id: str, exclude_message_id: str, limit: int = 20) -> list[dict]:
    """Return the last *limit* completed messages as {role, content} dicts."""
    from nucleus.models import ChatMessage

    qs = (
        ChatMessage.objects.filter(
            topic_id=topic_id,
            is_active=True,
            status=ChatMessage.Status.COMPLETED,
        )
        .exclude(id=exclude_message_id)
        .select_related("sender")
        .order_by("-created_at")[:limit]
    )
    history = []
    for m in reversed(list(qs)):
        role = "user" if m.sender_id else "assistant"
        if m.content:
            history.append({"role": role, "content": m.content})
    return history


# ---------------------------------------------------------------------------
# Serialiser
# ---------------------------------------------------------------------------

def _serialise(msg) -> dict:
    role = "user" if msg.sender_id else "assistant"
    sender_name = None
    sender_id = None
    if msg.sender_id:
        sender_name = (
            getattr(msg.sender, "display_name", None)
            or getattr(msg.sender, "email", None)
            or str(msg.sender_id)
        )
        sender_id = str(msg.sender_id)

    return {
        "id": str(msg.id),
        "role": role,
        "content": msg.content or "",
        "status": msg.status,
        "sender_name": sender_name,
        "sender_id": sender_id,
        "created_at": msg.created_at.isoformat(),
    }
