"""
Message search (W19): find a message across the chats a person can see.

Two halves, and only one of them decides anything. The worker answers "which
messages read like this" from the embeddings it already keeps; nucleus takes
those ids, keeps the ones this person may see, and builds every result from its
own rows. Authorisation never leaves here.

When the worker cannot answer -- not configured, down, nothing embedded yet --
the search still works: it falls back to a plain contains-match over the same
visible messages. Slower and literal, but a person typing in a search box gets
an answer rather than an empty box.
"""
import logging

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)

RESULTS_MAX = 25
PREVIEW_CHARS = 200
QUERY_MAX = 200
SEARCH_TIMEOUT_SECONDS = 5


def visible_topic_ids(user, company) -> list[str]:
    """Every topic this person can see, across the projects they can reach."""
    from authn.permissions.row_rules import visible_topic_ids as topic_ids

    return list(topic_ids(user, company))


def _rows(message_ids, topic_ids):
    from nucleus.models import ChatMessage
    return (
        ChatMessage.objects.filter(id__in=message_ids, topic_id__in=topic_ids, is_active=True)
        .exclude(message_type=ChatMessage.MessageType.SYSTEM)
        .select_related("topic", "topic__channel", "project", "sender")
    )


def _result(msg, query: str = "") -> dict:
    metadata = msg.metadata or {}
    content = msg.content or ""
    return {
        "message_id": str(msg.id),
        "topic_id": str(msg.topic_id),
        "topic_title": msg.topic.title,
        "channel_id": str(msg.topic.channel_id),
        "channel_name": msg.topic.channel.name if msg.topic.channel_id else "",
        "project_id": str(msg.project_id),
        "project_name": msg.project.name,
        "sender_name": metadata.get("persona_name") or (msg.sender.get_display_name() if msg.sender else None),
        "sender_type": getattr(msg.sender, "user_type", "human") if msg.sender else "system",
        "preview": _preview(content, query),
        "created_at": msg.created_at.isoformat(),
    }


def _preview(content: str, query: str) -> str:
    """A window around the first match, so a hit in a long message is visible."""
    text = " ".join(content.split())
    if not query:
        return text[:PREVIEW_CHARS]
    at = text.lower().find(query.lower())
    if at < 0:
        return text[:PREVIEW_CHARS]
    start = max(0, at - PREVIEW_CHARS // 3)
    window = text[start:start + PREVIEW_CHARS]
    return ("…" + window) if start else window


async def semantic_ids(company, query: str, project_ids: list[str], limit: int) -> list[str]:
    """Message ids the worker thinks match, best first, or [] when it cannot say."""
    url = getattr(settings, "NEXUS_AI_URL", "")
    key = getattr(settings, "INTERNAL_API_KEY", "")
    if not url:
        return []
    payload = {"company_id": str(company.id), "query": query, "top_k": limit, "project_ids": project_ids}
    try:
        async with httpx.AsyncClient(timeout=SEARCH_TIMEOUT_SECONDS) as client:
            response = await client.post(f"{url}/api/v1/search/messages/", json=payload, headers={"X-Internal-Key": key})
            response.raise_for_status()
            return [hit["message_id"] for hit in response.json().get("hits", []) if hit.get("message_id")]
    except Exception as exc:  # noqa: BLE001
        logger.info("[search] falling back to a plain search: %s", type(exc).__name__)
        return []


def literal(query: str, topic_ids: list[str], limit: int) -> list:
    """The fallback: the same visible messages, matched literally, newest first."""
    from nucleus.models import ChatMessage
    return list(
        ChatMessage.objects.filter(topic_id__in=topic_ids, is_active=True, content__icontains=query)
        .exclude(message_type=ChatMessage.MessageType.SYSTEM)
        .select_related("topic", "topic__channel", "project", "sender")
        .order_by("-created_at")[:limit]
    )


def order_by(ids: list[str], rows) -> list:
    """The rows the worker ranked, in its order — it knows which matched best."""
    by_id = {str(row.id): row for row in rows}
    return [by_id[i] for i in ids if i in by_id]
