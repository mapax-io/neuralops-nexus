"""
Message rows — save, update, list, serialise (Step 2 split,
docs/NUCLEUS-REVAMP.md; moved from chat/services.py with one addition: the
new engine's message_done fields — loaded_tools, used_tools,
retrieved_sources, embed_description — now land on the row).

Nothing here talks to the engine or to Centrifugo except
repost_untaken_nudges (which posts leftovers as ordinary messages).
"""
from __future__ import annotations

import logging
from datetime import timedelta

from asgiref.sync import sync_to_async
from django.db.models import Max
from django.utils import timezone

from .approvals import expire_open_approvals
from .realtime import publish_async
from .reasons import ORPHANED_RUN_REASON
from .stop_signals import stop_signals

logger = logging.getLogger(__name__)

USAGE_FIELDS = ("prompt_tokens", "output_tokens", "context_window")
# How many closed tool calls a reply keeps on its row: enough to audit a
# long agentic run, small enough to ride in the message metadata.
ACTIVITY_TRAIL_MAX = 50
ORPHAN_AFTER_SECONDS = 180


# ── Sessions (@session) ───────────────────────────────────────────────────────

def get_active_session(user_id, topic_id):
    """
    Return the active ChatSession for this user+topic, or None.
    Returns None if no session exists or if it has expired.
    """
    from django.db.models import Prefetch
    from nucleus.models import ChatSession, Persona

    session = ChatSession.objects.filter(
        user_id=user_id,
        topic_id=topic_id,
    ).prefetch_related(
        Prefetch(
            "personas",
            queryset=Persona.objects.select_related(
                "model", "advisor_model", "prompt",
            ).prefetch_related("mcp_servers"),
        )
    ).first()

    if session is None:
        return None

    # Check expiry — hard-delete expired session and return None
    if session.expires_at <= timezone.now():
        session.delete()
        return None

    return session


def create_session(user, topic, personas: list, timeout_minutes: int = 30):
    """
    Create (or replace) a ChatSession for this user+topic.
    """
    from nucleus.models import ChatSession

    close_session(user.id, topic.id)

    expires_at = timezone.now() + timedelta(minutes=timeout_minutes)
    session = ChatSession.objects.create(
        user=user,
        topic=topic,
        expires_at=expires_at,
    )
    if personas:
        session.personas.set(personas)

    return session


def close_session(user_id, topic_id) -> list[str] | None:
    """
    Close the active session for this user+topic. Hard-deleted (ephemeral
    state). Returns the closed session's persona names, or None if no
    session existed — so the caller can name them in the system message.
    """
    from nucleus.models import ChatSession

    session = (
        ChatSession.objects.filter(user_id=user_id, topic_id=topic_id)
        .prefetch_related("personas")
        .first()
    )
    if not session:
        return None
    names = [p.name for p in session.personas.all()]
    session.delete()
    return names


# ── AI reply rows ─────────────────────────────────────────────────────────────

def create_ai_message(company, project, topic, persona, render_as: str = "text", triggered_by=None, runbook_run: dict | None = None) -> dict:
    """
    Pre-create a PENDING ChatMessage for the AI response. `triggered_by` is the
    person who called the persona (the sender, a schedule's creator, the one who
    asked before a plan was approved): the reply is theirs to stop (W22).
    """
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
        metadata={
            "role": "assistant",
            "persona_id": str(persona.id),
            "persona_name": persona.name,   # display name for serializer
            "render_as": render_as,
            **({"triggered_by_id": str(triggered_by.id), "triggered_by_name": triggered_by.get_display_name()} if triggered_by is not None else {}),
            # W6: which runbook step this reply is ({id, title, step, of}).
            **({"runbook_run": runbook_run} if runbook_run else {}),
        },
    )
    return serialise(msg)


def set_message_status(message_id: str, status: str, content: str | None = None) -> None:
    """One status move (e.g. PENDING→STREAMING, STREAMING→PAUSED), optionally
    keeping the text streamed so far — never touches the rest of the row."""
    from nucleus.models import ChatMessage
    fields = {"status": status}
    if content is not None:
        fields["content"] = content
    ChatMessage.objects.filter(id=message_id).update(**fields)


def update_ai_message(
    message_id: str,
    content: str,
    render_as: str = "text",
    output_type: str = "text",
    stopped: bool = False,
    usage: dict | None = None,
    activity_trail: list | None = None,
    preflight: dict | None = None,
    answered_by_model: str | None = None,
    nudges: list[str] | None = None,
    loaded_tools: list[str] | None = None,
    used_tools: list[str] | None = None,
    retrieved_sources: list | None = None,
    embed_description: str | None = None,
) -> None:
    """Update the AI message content and mark COMPLETED. `stopped`: the reader ended it; content is partial."""
    from nucleus.models import ChatMessage

    msg = ChatMessage.objects.filter(id=message_id).first()
    if not msg:
        return

    # Merge render_as into existing metadata
    metadata = dict(msg.metadata or {})
    metadata["render_as"] = render_as
    metadata["output_type"] = output_type
    expire_open_approvals(metadata)
    if stopped:
        metadata["stopped"] = True
    if usage:
        metadata["usage"] = usage
    if activity_trail:
        metadata["activity_trail"] = activity_trail
    if answered_by_model:
        metadata["answered_by_model"] = answered_by_model
    if nudges:
        metadata["nudges"] = list(nudges)
    if preflight:
        metadata["preflight"] = preflight
    # Step 2: the new engine's message_done extras — stored for history replay
    # and (used_tools/retrieved_sources) later carried as vector metadata.
    if loaded_tools is not None:
        metadata["loaded_tools"] = list(loaded_tools)
    if used_tools is not None:
        metadata["used_tools"] = list(used_tools)
    if retrieved_sources is not None:
        metadata["retrieved_sources"] = list(retrieved_sources)
    if embed_description:
        metadata["embed_description"] = embed_description

    ChatMessage.objects.filter(id=message_id).update(
        content=content,
        status=ChatMessage.Status.COMPLETED,
        metadata=metadata,
    )


def fail_ai_message(message_id: str, error: str, display_content: str | None = None, activity_trail: list | None = None) -> None:
    """
    Mark the AI placeholder message FAILED instead of COMPLETED. Without
    this, a failed trigger lands on "completed" with blank content —
    indistinguishable from the AI genuinely replying with nothing.

    display_content overrides the generic placeholder — used for errors
    the user should actually see verbatim (e.g. mcp_reauth_required). The
    real error is always kept in metadata.error_detail for debugging.
    """
    from nucleus.models import ChatMessage
    msg = ChatMessage.objects.filter(id=message_id).first()
    if not msg:
        return
    metadata = dict(msg.metadata or {})
    metadata["error_detail"] = error
    expire_open_approvals(metadata)
    if activity_trail:
        metadata["activity_trail"] = activity_trail
    ChatMessage.objects.filter(id=message_id).update(
        content=display_content or "Something went wrong generating this response.",
        status=ChatMessage.Status.FAILED,
        metadata=metadata,
    )


def remember_tool_call(trail: list, event: dict) -> None:
    """Append a worker tool_call_end to a reply's trail, keeping the newest ACTIVITY_TRAIL_MAX."""
    result = event.get("tool_result") or {}
    name = (result.get("name") or "").strip()
    if not name:
        return
    trail.append({
        "tool": name,
        "ok": bool(result.get("ok")),
        "duration_ms": int(result.get("duration_ms") or 0),
        "preview": result.get("preview"),
        "error": result.get("error"),
        # The page a web tool went to -- the app opens it beside the chat (W9).
        "url": result.get("url"),
    })
    del trail[:-ACTIVITY_TRAIL_MAX]


def usage_from(event: dict) -> dict | None:
    """The worker's usage on a message_done event, or None when it sent nothing."""
    values = {k: event.get(k) for k in USAGE_FIELDS}
    return values if any(v is not None for v in values.values()) else None


def with_usage(payload: dict, usage: dict | None) -> dict:
    """The three usage fields on a published message_done -- always present, null when unknown."""
    payload.update({k: (usage or {}).get(k) for k in USAGE_FIELDS})
    return payload


# ── Read messages ─────────────────────────────────────────────────────────────

def list_messages(topic_id: str, limit: int = 100, before_sequence: int = None) -> list[dict]:
    """
    Return up to `limit` messages in a topic, oldest first. Pass
    `before_sequence` to page further back (sequence is the cursor: a
    strictly increasing per-topic integer, no timestamp ties).
    """
    from nucleus.models import ChatMessage

    reap_orphaned_replies(topic_id)

    qs = ChatMessage.objects.filter(topic_id=topic_id, is_active=True)
    if before_sequence is not None:
        qs = qs.filter(sequence__lt=before_sequence)

    qs = qs.select_related("sender").order_by("-sequence")[:limit]
    return [serialise(m) for m in reversed(list(qs))]


def reap_orphaned_replies(topic_id: str, older_than_seconds: int = ORPHAN_AFTER_SECONDS) -> list[str]:
    """
    A persona reply still PENDING/STREAMING minutes after it started has no
    relay left to finish it — nucleus restarted mid-run. Fail it with that
    reason. A PAUSED reply is NOT an orphan: it is parked on purpose,
    waiting for a person, however long they take. Done lazily, when history
    is read or a stop is asked for; returns the ids it failed.
    """
    from nucleus.models import ChatMessage

    cutoff = timezone.now() - timedelta(seconds=older_than_seconds)
    live = [ChatMessage.Status.PENDING, ChatMessage.Status.STREAMING]
    orphans = list(
        ChatMessage.objects.filter(topic_id=topic_id, status__in=live, created_at__lt=cutoff, metadata__has_key="persona_id")
        .values_list("id", flat=True)
    )
    for msg_id in orphans:
        fail_ai_message(str(msg_id), "orphaned: no relay finished this reply", ORPHANED_RUN_REASON)
    return [str(i) for i in orphans]


# ── Write messages ────────────────────────────────────────────────────────────

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
    return serialise(msg)


def save_user_message(company, project, topic, user, content: str) -> dict:
    """Save a human message and return its serialised form."""
    from nucleus.models import ChatMessage

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
    return serialise(msg)


# ── Context sources for TriggerJob ────────────────────────────────────────────

def build_context_sources(topic, company, persona=None) -> list[dict]:
    """
    Build the context_sources list for TriggerJob: a ChatContext ref
    (semantic search over past messages) and any READY file/web sources
    attached to the topic. (The Recall source left with the feature,
    2026-10-22.)
    """
    sources = [{
        "source_id": str(topic.id),
        "type": "chat",
        "label": "Chat History",
        "collection_id": f"company_{company.id}_chat",
    }]

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


# ── Serialiser ────────────────────────────────────────────────────────────────

def serialise(msg) -> dict:
    metadata = msg.metadata or {}
    # For AI persona messages, use the stored persona_name rather than the
    # shadow user's auto-generated username (e.g. "user_28").
    if msg.sender and metadata.get("persona_name"):
        sender_name = metadata["persona_name"]
    elif msg.sender:
        sender_name = msg.sender.get_display_name()
    else:
        sender_name = None
    return {
        "id": str(msg.id),
        "type": "message",
        "message_type": msg.message_type,
        "content": msg.content or "",
        "render_as": metadata.get("render_as", "text"),
        "output_type": metadata.get("output_type", "text"),
        "stopped": bool(metadata.get("stopped")),
        "status": msg.status,  # pending|streaming|completed|failed|cancelled|paused
        "activity_trail": metadata.get("activity_trail") or [],
        "preflight": metadata.get("preflight"),
        "approvals": metadata.get("approvals") or [],
        # Step 2: pending questions (item 5) — answered through the resume road.
        "questions": metadata.get("questions") or [],
        "answered_by_model": metadata.get("answered_by_model"),
        "nudges": metadata.get("nudges") or [],
        "usage": metadata.get("usage"),
        # Step 2: the new engine's message_done extras.
        "used_tools": metadata.get("used_tools") or [],
        "retrieved_sources": metadata.get("retrieved_sources") or [],
        "sender_name": sender_name,
        "sender_id": str(msg.sender_id) if msg.sender_id else None,
        "sender_avatar": msg.sender.get_avatar_url() if msg.sender else None,  # #148
        "sender_type": getattr(msg.sender, "user_type", "human") if msg.sender else "system",
        "persona_id": metadata.get("persona_id"),
        "triggered_by_id": metadata.get("triggered_by_id"),
        "triggered_by_name": metadata.get("triggered_by_name"),
        "runbook_run": metadata.get("runbook_run"),
        "sequence": msg.sequence,
        "created_at": msg.created_at.isoformat(),
    }


# Step 2 compatibility: the old private name, used across tests and callers.
_serialise = serialise


# ── Nudges + stop ─────────────────────────────────────────────────────────────

def request_nudge_for_message(topic, message_id: str, user) -> str:
    """
    Whether `user` may add to a reply that is still running here (W8 Nudge):
    "nudging", or "not_found" / "finished" / "not_owner" as for a stop -- a
    reply is its caller's to steer. Sync; the caller wraps it.
    """
    from nucleus.models import ChatMessage

    msg = ChatMessage.objects.filter(id=message_id, topic=topic).first()
    if not msg or not (msg.metadata or {}).get("persona_id"):
        return "not_found"
    if msg.status not in (ChatMessage.Status.PENDING, ChatMessage.Status.STREAMING):
        return "finished"
    owner_id = (msg.metadata or {}).get("triggered_by_id")
    if owner_id and owner_id != str(user.id):
        return "not_owner"
    return "nudging"


async def repost_untaken_nudges(company, project, topic, msg_id: str, channel: str) -> int:
    """
    Never lost: a nudge the persona did not reach becomes an ordinary
    message from the person who sent it. Returns how many were posted.
    """
    from nucleus.models import User as _User
    leftovers = await stop_signals().take_nudges(msg_id)
    posted = 0
    for nudge in leftovers:
        user = await sync_to_async(lambda uid: _User.objects.filter(id=uid).first())(nudge.get("user_id"))
        text = (nudge.get("text") or "").strip()
        if not user or not text:
            continue
        try:
            msg = await sync_to_async(save_user_message)(company, project, topic, user, text)
            await publish_async(channel, msg)
            posted += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("[nudge] could not repost a nudge for %s: %s", msg_id, exc)
    return posted


def request_stop_for_message(topic, message_id: str, user=None) -> str:
    """
    Ask the relay to end a persona reply that is still streaming here.
    Returns "stopping", "not_found", "finished", "orphaned", or "not_owner"
    — a reply is its caller's to stop (W22). Sync; the caller wraps it.
    """
    from nucleus.models import ChatMessage

    msg = ChatMessage.objects.filter(id=message_id, topic=topic).first()
    if not msg or not (msg.metadata or {}).get("persona_id"):
        return "not_found"
    if msg.status not in (ChatMessage.Status.PENDING, ChatMessage.Status.STREAMING):
        return "finished"
    owner_id = (msg.metadata or {}).get("triggered_by_id")
    if user is not None and owner_id and owner_id != str(user.id):
        return "not_owner"
    if msg.created_at < timezone.now() - timedelta(seconds=ORPHAN_AFTER_SECONDS):
        fail_ai_message(str(msg.id), "orphaned: no relay finished this reply", ORPHANED_RUN_REASON)
        return "orphaned"
    return "stopping"
