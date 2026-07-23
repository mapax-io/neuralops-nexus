"""
Chat API — human-to-human messaging + AI trigger (M3 + M7).

Flow:
    POST /messages/
        1. Validate project / channel / topic membership
        2. Save message to DB (sender = authenticated user)
        3. Fire-and-forget async publish to Centrifugo topic:{topic_id}
        4. Fire-and-forget async embed to nexus-ai (M2)
        5. Detect @output_type directive (M7) — strip from message, pass to trigger
        6. Detect @persona mention (M3) — trigger AI response fire-and-forget
        7. Return immediately — React receives the message via WebSocket

    GET /messages/
        Return last 100 messages (history) when a topic is opened.
"""
import asyncio
import logging
import re
from typing import List

logger = logging.getLogger(__name__)

from asgiref.sync import sync_to_async
from ninja import Router
from ninja.errors import HttpError

from authn.auth import SupabaseBearer
from chat.schema import MessageOut, SendMessageIn, SendMessageOut
from chat import services as chat_svc
from workspace import services as ws_svc
from intelligence import services as intel_svc

# Matches @Word — finds the first @mention in the message
_MENTION_RE = re.compile(r'@([\w]+)')

router = Router(tags=["Chat"], auth=SupabaseBearer())


# ── Helpers ────────────────────────────────────────────────────────────────────

def _resolve_topic_sync(request, project_id: str, channel_id: str, topic_id: str):
    """Resolve and validate all path params — raises HttpError on any miss."""
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


_resolve_topic = sync_to_async(_resolve_topic_sync)
_list_messages = sync_to_async(chat_svc.list_messages)
_save_user_message = sync_to_async(chat_svc.save_user_message)
_get_persona_by_mention = sync_to_async(intel_svc.get_persona_by_mention)
_list_messages_sync = sync_to_async(chat_svc.list_messages)


# ── GET /messages/ — load history ─────────────────────────────────────────────

@router.get(
    "/{project_id}/channels/{channel_id}/topics/{topic_id}/messages/",
    response=List[MessageOut],
)
async def list_messages(
    request,
    project_id: str,
    channel_id: str,
    topic_id: str,
):
    """
    Return the last 100 messages in a topic, oldest first.
    Called by React on topic open to populate history.
    """
    await _resolve_topic(request, project_id, channel_id, topic_id)
    return await _list_messages(topic_id)


# ── POST /messages/ — send message ────────────────────────────────────────────

@router.post(
    "/{project_id}/channels/{channel_id}/topics/{topic_id}/messages/",
    response=SendMessageOut,
)
async def send_message(
    request,
    project_id: str,
    channel_id: str,
    topic_id: str,
    payload: SendMessageIn,
):
    """
    Save a human message, broadcast via Centrifugo, embed, and trigger AI if mentioned.

    Both publish and embed are fire-and-forget (asyncio.create_task) so this
    endpoint returns immediately — latency stays low regardless of AI/Centrifugo.
    """
    if not payload.content.strip():
        raise HttpError(400, "Message content cannot be empty.")

    if len(payload.content) > 4000:
        raise HttpError(400, "Message too long (max 4000 characters). Attach large text as a context source.")

    company, user, project, channel, topic = await _resolve_topic(
        request, project_id, channel_id, topic_id
    )

    # 1. Save to DB (original message with @directives intact for display)
    msg = await _save_user_message(
        company=company,
        project=project,
        topic=topic,
        user=user,
        content=payload.content.strip(),
    )

    # 2. Publish to Centrifugo — fire and forget
    centrifugo_channel = chat_svc.topic_channel(topic_id)
    asyncio.create_task(chat_svc.publish_async(centrifugo_channel, msg))

    # 3. Embed to nexus-ai — fire and forget (M2)
    asyncio.create_task(
        chat_svc.embed_message_async(
            message_id=msg["id"],
            company_id=str(company.id),
            sequence=msg["sequence"],
            topic_id=topic_id,
            channel_id=channel_id,
            project_id=project_id,
            sender_id=msg["sender_id"],
            sender_name=msg["sender_name"],
            sender_type=msg["sender_type"],
            content=msg["content"],
            created_at=msg["created_at"],
        )
    )

    # 4. M7: Extract @output_type directive before persona detection
    #    e.g. "@Nova show me sales @chart" → output_type="chart", clean="@Nova show me sales"
    output_type, clean_message = chat_svc.extract_output_type(payload.content.strip())

    # 5. Detect @persona mention — trigger AI response fire-and-forget (M3)
    mention_match = _MENTION_RE.search(clean_message)
    if mention_match:
        mention_name = mention_match.group(1)
        persona = await _get_persona_by_mention(company, mention_name)
        logger.info("[chat/api] mention=%s persona=%s model=%s", mention_name, persona, getattr(persona, 'model', None))
        if persona and persona.model:
            raw_history = await _list_messages_sync(topic_id, limit=20)
            ai_history = []
            for m in raw_history:
                # Skip the message we just saved (passed separately as user_message,
                # so including it here would send it to the LLM twice).
                if m["id"] == msg["id"]:
                    continue
                # Skip empty / PENDING AI messages
                if not m["content"]:
                    continue
                role = "user" if m["sender_type"] == "human" else "assistant"
                render_as = m.get("render_as", "text")
                output_type_val = m.get("output_type", "text")
                content = m["content"].strip()
                # Skip botched AI responses — they poison the LLM context and
                # cause it to keep reproducing the same wrong pattern.
                if role == "assistant":
                    _VISUAL_TYPES = {"chart", "table", "diagram", "html", "form"}
                    # Case 1: Expected HTML but got plain text (old behaviour before
                    # our "no markers → text" rule)
                    if render_as == "html" and not (
                        content.startswith("<!DOCTYPE") or content.startswith("<html")
                    ):
                        continue
                    # Case 2: Visual output type but no markers found — fell back to
                    # render_as="text" (our new rule). The content is a conversational
                    # failure like "I've reviewed the provided request.".
                    if output_type_val in _VISUAL_TYPES and render_as == "text":
                        continue
                ai_history.append({
                    "role": role,
                    "content": m["content"],
                    "sender_name": m["sender_name"],
                })
            asyncio.create_task(
                chat_svc.trigger_ai_response_async(
                    company=company,
                    project=project,
                    topic=topic,
                    persona=persona,
                    user_message=clean_message,  # @output_type stripped
                    history=ai_history,
                    topic_id=topic_id,
                    output_type=output_type,     # M7: "auto" | "chart" | "code" | ...
                )
            )

    # 6. Return immediately
    return {
        "message": msg,
        "channel": centrifugo_channel,
    }
