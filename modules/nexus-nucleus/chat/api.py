"""
Chat API — human-to-human messaging + AI trigger (M3 + M7 + M7.1).

Flow:
    POST /messages/
        1. Validate project / channel / topic membership
        2. Parse every @directive up front (chat/services.py:MessageDirectives)
           — @session, @session close, @output_type, @persona mentions
        3. Save message to DB (sender = authenticated user, raw text
           with @directives intact, so the sender sees what they typed)
        4. Fire-and-forget async embed to nexus-ai (M2), right after the
           save — uses the directive-stripped text, not the raw
           @session/@chart control directives, since those aren't
           meaningful content to search on. Whether this should skip
           firing based on the eventual routing outcome is a separate,
           still-open question (#128) — not entangled with save/publish
           ordering for now
        5. Fire-and-forget async publish to Centrifugo topic:{topic_id}
        6. Resolve @mentions to Persona objects (M3 + M7.1)
        7. Apply session routing priority (M7.1), using the directives
           parsed in step 2:
              (a) @session close                → close session, no AI trigger
              (b) @mentions + @session          → close old, open new session,
                                                  trigger mentioned personas
              (c) @mentions (no @session)       → trigger mentioned only,
                                                  session unchanged
              (d) no @mention, session active   → trigger all session personas
              (e) no @mention, no session       → no AI trigger
        8. Return immediately — React receives the message via WebSocket

    GET /messages/
        Return up to `limit` messages (default 100), oldest first. Pass
        before_sequence to page further back in history -- see
        chat/services.py:list_messages.
"""
import asyncio
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)

from asgiref.sync import sync_to_async
from ninja import Query, Router
from ninja.errors import HttpError

from authn.auth import SupabaseBearer
from chat.schema import MessageOut, SendMessageIn, SendMessageOut
from chat import services as chat_svc
from chat.services import MessageDirectives
from workspace import services as ws_svc
from intelligence import services as intel_svc

router = Router(tags=["Chat"], auth=SupabaseBearer())


# ── Helpers ────────────────────────────────────────────────────────────────────

def _resolve_topic_sync(request, project_id: str, channel_id: str, topic_id: str):
    """
    Resolve and validate all path params — raises HttpError on any miss.

    Channel/topic are resolved through list_channels()/list_topics() (the
    same visible_channels/visible_topics row-visibility used by the sidebar
    list endpoints in workspace/api.py) rather than a plain ID lookup, so a
    channel or topic this user can't see can't be reached here either just
    because they're a member of the parent project. See the git history /
    prior chat discussion for the still-open half of this: a user with
    ONLY a Topic-scoped RoleAssignment (no Project-scope role) still fails
    the project.view check below before we even get here.
    """
    user = request.auth
    company = ws_svc.get_company()
    if not company:
        raise HttpError(503, "Server not initialised.")

    project = ws_svc.get_project(company, user, project_id)
    if not project:
        raise HttpError(404, "Project not found.")

    channel = ws_svc.list_channels(user, project).filter(id=channel_id).first()
    if not channel:
        raise HttpError(404, "Channel not found.")

    topic = ws_svc.list_topics(user, channel).filter(id=topic_id).first()
    if not topic:
        raise HttpError(404, "Topic not found.")

    return company, user, project, channel, topic


_resolve_topic = sync_to_async(_resolve_topic_sync)
_list_messages = sync_to_async(chat_svc.list_messages)
_save_user_message = sync_to_async(chat_svc.save_user_message)
_get_persona_by_mention = sync_to_async(intel_svc.get_persona_by_mention)
_get_active_session = sync_to_async(chat_svc.get_active_session)
_create_session = sync_to_async(chat_svc.create_session)
_close_session = sync_to_async(chat_svc.close_session)
_save_system_message = sync_to_async(chat_svc.save_system_message)


def _get_session_timeout_sync(company) -> int:
    """Return session_timeout_minutes from company AI config, or default 30."""
    try:
        return company.ai_config.session_timeout_minutes
    except Exception:  # ai_config may not exist yet
        return 30


_get_session_timeout = sync_to_async(_get_session_timeout_sync)


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
    limit: int = Query(default=100, le=200),
    before_sequence: Optional[int] = Query(default=None),
):
    """
    Return up to `limit` messages in a topic, oldest first. Called by React
    on topic open to populate history (no before_sequence -- gets the most
    recent `limit`), and again on scroll-to-top with before_sequence set
    to the oldest loaded message's sequence, to page further back.

    Resolving the topic here is purely the visibility/permission check
    (project.view / channel.list / topic.list) -- the returned objects
    aren't otherwise needed, since the actual message query below just
    uses the already-known, now-validated topic_id.
    """
    await _resolve_topic(request, project_id, channel_id, topic_id)
    return await _list_messages(topic_id, limit=limit, before_sequence=before_sequence)


# ── POST /messages/ — send message ────────────────────────────────────────────

@router.post("/{project_id}/channels/{channel_id}/topics/{topic_id}/typing/")
async def send_typing(request, project_id: str, channel_id: str, topic_id: str):
    """
    Fire-and-forget: broadcast a user_typing event to everyone else
    subscribed to this topic's Centrifugo channel. Called by
    MessageInput.tsx, throttled client-side while there's text in the box
    -- no server-side rate limiting needed on top of that. No DB write;
    purely a Centrifugo publish. Receiving clients expire the indicator
    themselves after a few seconds of no further pings -- there's no
    explicit "stopped typing" counterpart event. See #141.
    """
    company, user, project, channel, topic = await _resolve_topic(
        request, project_id, channel_id, topic_id
    )
    asyncio.create_task(chat_svc.publish_async(chat_svc.topic_channel(topic_id), {
        "type": "user_typing",
        "id": str(user.id),
        "name": user.get_display_name(),
        "avatar": user.get_avatar_url(),
    }))
    return {"ok": True}


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

    Content is already validated + stripped by SendMessageIn's own field
    validator (chat/schema.py) before this function ever runs -- no empty-
    check or length-check here, and payload.content is used as-is below,
    not re-stripped.
    """
    company, user, project, channel, topic = await _resolve_topic(
        request, project_id, channel_id, topic_id
    )

    # 1. Parse every @directive up front -- see chat/services.py:MessageDirectives.
    #    Everything below just reads these fields; nothing parses text itself.
    directives = MessageDirectives(payload.content)

    # 2. Save to DB (original message with @directives intact for display)
    msg = await _save_user_message(
        company=company,
        project=project,
        topic=topic,
        user=user,
        content=payload.content,
    )

    # 3. Embed to nexus-ai — fire and forget (M2), right after the save.
    #    Uses the directive-stripped text (session/output_type control
    #    directives removed), not the raw content, since those directives
    #    aren't meaningful semantic content to search on later. Whether
    #    this should skip firing based on the routing outcome (e.g. a
    #    pure @session close) is a separate, still-open question -- see
    #    #128 -- deliberately not entangled with save/publish ordering.
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
            content=directives.clean_message,
            created_at=msg["created_at"],
        )
    )

    # 4. Publish to Centrifugo — fire and forget
    centrifugo_channel = chat_svc.topic_channel(topic_id)
    asyncio.create_task(chat_svc.publish_async(centrifugo_channel, msg))

    # 5. Resolve @mentions to Persona objects (parallel)
    mentioned_personas = []
    for name in directives.mention_names:
        # Personas are project-owned -- scoped to this topic's project, not
        # the whole company (see intelligence/services.py:get_persona_by_mention).
        p = await _get_persona_by_mention(project, name)
        if p:
            mentioned_personas.append(p)
            logger.info("[chat/api] mention=%s resolved persona=%s", name, p)

    # 6. Apply session routing priority

    if directives.is_session_close:
        # Rule 1: @session close — close session, no AI trigger
        closed = await _close_session(user.id, topic.id)
        logger.warning("[chat/api] session closed user=%s topic=%s found=%s", user.id, topic_id, closed is not None)
        # Name the personas the session was with (matches the open message), so
        # the pill reads "Session with @X closed." not a bare "Session closed."
        names = ", ".join(f"@{n}" for n in (closed or []))
        sys_msg = await _save_system_message(
            company=company, project=project, topic=topic,
            content=f"Session with {names} closed." if names else "Session closed.",
        )
        asyncio.create_task(chat_svc.publish_async(
            centrifugo_channel, {**sys_msg, "type": "message"}
        ))

    elif mentioned_personas and directives.has_session_open:
        # Rule 2: @mentions + @session — open new session with mentioned personas.
        # If a session is already open here, close it FIRST and announce it — so
        # switching personas mid-topic shows the old session ending in chat.
        # (create_session closes the previous one silently; the announce has to
        # happen at the API layer, which is the only place that can publish.)
        prior = await _close_session(user.id, topic.id)
        if prior:
            prior_names = ", ".join(f"@{n}" for n in prior)
            close_msg = await _save_system_message(
                company=company, project=project, topic=topic,
                content=f"Session with {prior_names} closed.",
            )
            asyncio.create_task(chat_svc.publish_async(
                centrifugo_channel, {**close_msg, "type": "message"}
            ))
        timeout = await _get_session_timeout(company)
        await _create_session(user, topic, mentioned_personas, timeout)
        persona_names = ", ".join(f"@{p.name}" for p in mentioned_personas)
        logger.warning(
            "[chat/api] session opened personas=%s timeout=%sm",
            [p.name for p in mentioned_personas], timeout,
        )
        sys_msg = await _save_system_message(
            company=company, project=project, topic=topic,
            content=f"Session with {persona_names} opened ({timeout} min). Plain messages will go to them automatically.",
        )
        asyncio.create_task(chat_svc.publish_async(
            centrifugo_channel, {**sys_msg, "type": "message"}
        ))
        # Only trigger personas if there is actual content beyond the @mention
        if directives.message_without_mentions():
            await _trigger_personas(mentioned_personas, company, project, topic,
                                     topic_id, msg, directives.clean_message, 
                                     directives.output_type, directives.swarm)

    elif mentioned_personas:
        # Rule 3: @mentions (no @session) — trigger only mentioned, session unchanged
        await _trigger_personas(mentioned_personas, company, project, topic,
                                 topic_id, msg, directives.clean_message,
                                 directives.output_type, directives.swarm)

    else:
        # Rules 4 + 5: no explicit mention — check session
        active_session = await _get_active_session(user.id, topic.id)
        if active_session:
            # Rule 4: session active — trigger all session personas
            session_personas = list(active_session.personas.all())
            logger.warning(
                "[chat/api] session auto-trigger personas=%s",
                [p.name for p in session_personas],
            )
            await _trigger_personas(session_personas, company, project, topic,
                                     topic_id, msg, directives.clean_message,
                                     directives.output_type, directives.swarm)
        # Rule 5: no mention, no session — human-only message, nothing to do

    # 7. Return immediately
    return {
        "message": msg,
        "channel": centrifugo_channel,
    }


async def _trigger_personas(
    personas: list,
    company,
    project,
    topic,
    topic_id: str,
    msg: dict,
    clean_message: str,
    output_type: str,
    swarm: bool
) -> None:
    """
    Fire AI trigger tasks for each persona in parallel.
    Spawns one asyncio task per persona. Only triggers personas that have
    a model configured -- a cheap existence check, not a judgment about the
    model's actual configuration, so it stays here. (The old source_type
    model/agent split is gone; see the gate in the loop below.)

    History is NOT built here anymore -- nexus-ai fetches and filters it
    itself, per persona, right before building that persona's prompt (see
    #131). This function's only job is deciding WHO to trigger.
    """
    if not personas:
        return
    # Turn off swarm mode if only one persona is mentioned
    swarm = swarm and len(personas) > 1

    if swarm:
        asyncio.create_task(
            chat_svc.trigger_ai_swarm_response_async(
                company=company,
                project=project,
                topic=topic,
                personas=personas,
                user_message=clean_message,
                user_message_id=msg["id"],
                topic_id=topic_id,
                output_type=output_type,
            )
        )

    else:
        for persona in personas:
            # One gate now, where there used to be two. A persona no longer
            # has a source_type -- it has exactly one ModelConfig, optionally
            # an advisor, and zero or more MCP servers, and "has tools" is
            # just "mcp_servers is non-empty". model is NOT NULL at the
            # database level, so this can only be falsy if the row it points
            # at was soft-deleted.
            if not persona.model_id:
                logger.info("[chat/api] skipping persona=%s (no model configured)", persona)
                continue
            asyncio.create_task(
                chat_svc.trigger_ai_response_async(
                    company=company,
                    project=project,
                    topic=topic,
                    persona=persona,
                    user_message=clean_message,
                    user_message_id=msg["id"],
                    topic_id=topic_id,
                    output_type=output_type,
                )
            )


        

