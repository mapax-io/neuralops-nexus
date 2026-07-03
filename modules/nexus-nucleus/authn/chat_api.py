"""
Chat API — human-to-human messaging.

Endpoints:
    GET  /api/v1/projects/{project_id}/channels/{channel_id}/topics/{topic_id}/messages/
    POST /api/v1/projects/{project_id}/channels/{channel_id}/topics/{topic_id}/messages/

Flow (Phase 1 — human-to-human):
    POST /messages/
        1. Save message to DB (sender = authenticated user)
        2. Publish to Centrifugo channel "topic:{topic_id}"
        3. Return the saved message + channel name

    React side:
        - Subscribes to "topic:{topic_id}" on Centrifugo WebSocket
        - Receives { type: "message", ... } events in real time
        - Loads history via GET /messages/ on topic open

Phase 2 extension (AI-to-human) — additive, nothing here changes:
    After step 1, detect @persona mentions → trigger nexus-ai async
    nexus-ai streams tokens back → publish { type: "token" / "done" } to same channel
"""
from typing import List

from ninja import Router
from ninja.errors import HttpError

from .auth import SupabaseBearer
from .chat_schema import MessageOut, SendMessageIn, SendMessageOut
from . import chat_services as chat_svc
from . import workspace_services as ws_svc

router = Router(tags=["Chat"], auth=SupabaseBearer())


def _resolve_topic(request, project_id: str, channel_id: str, topic_id: str):
    """Resolve company, user, project, channel, topic — raises on any 404."""
    user = request.auth
    company = ws_svc.get_company()
    if not company:
        raise HttpError(503, "Server not initialised.")

    project = ws_svc.get_project(company, user, project_id)
    if not project:
        raise HttpError(404, "Project not found.")

    channel = ws_svc.get_channel(company, project, channel_id)
    if not channel:
        raise HttpError(404, "Channel not found.")

    topic = ws_svc.get_topic(company, project, channel, topic_id)
    if not topic:
        raise HttpError(404, "Topic not found.")

    return company, user, project, channel, topic


# ── List messages ─────────────────────────────────────────────────────────────

@router.get(
    "/{project_id}/channels/{channel_id}/topics/{topic_id}/messages/",
    response=List[MessageOut],
)
def list_messages(request, project_id: str, channel_id: str, topic_id: str):
    """
    Return the last 100 messages in a topic, oldest first.
    Called by React when a topic is opened to load history.
    """
    _resolve_topic(request, project_id, channel_id, topic_id)
    return chat_svc.list_messages(topic_id)


# ── Send message ──────────────────────────────────────────────────────────────

@router.post(
    "/{project_id}/channels/{channel_id}/topics/{topic_id}/messages/",
    response=SendMessageOut,
)
def send_message(
    request,
    project_id: str,
    channel_id: str,
    topic_id: str,
    payload: SendMessageIn,
):
    """
    Save a human message and broadcast it to all topic subscribers via Centrifugo.

    Returns the saved message and the Centrifugo channel name so React
    knows where to subscribe for live updates.
    """
    company, user, project, channel, topic = _resolve_topic(
        request, project_id, channel_id, topic_id
    )

    if not payload.content.strip():
        raise HttpError(400, "Message content cannot be empty.")

    # 1. Save to DB
    msg = chat_svc.save_user_message(
        company=company,
        project=project,
        topic=topic,
        user=user,
        content=payload.content.strip(),
    )

    # 2. Publish to Centrifugo — all subscribers receive it instantly
    centrifugo_channel = chat_svc.topic_channel(topic_id)
    chat_svc.publish(centrifugo_channel, msg)

    # 3. Return message + channel name
    return {
        "message": msg,
        "channel": centrifugo_channel,
    }
