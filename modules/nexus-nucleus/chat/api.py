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
from authn.permissions.checker import PermissionChecker
from chat.events import mention_refused_event
from chat.schema import MessageSearchOut, MessageOut, SendMessageIn, SendMessageOut, StopMessageOut, PreflightDecisionIn, PreflightDecisionOut, ToolApprovalDecisionIn, ToolApprovalDecisionOut, NudgeIn
from chat import services as chat_svc
from chat.services import MessageDirectives
from workspace import services as ws_svc
from intelligence import services as intel_svc

router = Router(tags=["Chat"], auth=SupabaseBearer())
# Search is not under a project: it looks across every chat a person can see.
search_router = Router(tags=["Search"], auth=SupabaseBearer())


# ── Helpers ────────────────────────────────────────────────────────────────────

def _resolve_topic_sync(request, project_id: str, channel_id: str, topic_id: str):
    """
    Resolve and validate all path params — raises HttpError on any miss.

    Channel/topic are resolved through list_channels()/list_topics() (the
    same visible_channels/visible_topics row-visibility used by the sidebar
    list endpoints in workspace/api.py) rather than a plain ID lookup, so a
    channel or topic this user can't see can't be reached here either just
    because they're a member of the parent project. A user with ONLY a
    Topic-scoped RoleAssignment gets through get_project() via its
    reachable-projects fallback, then sees just their topic here.
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
_get_routine_by_name = sync_to_async(intel_svc.get_routine_by_name)
_get_active_session = sync_to_async(chat_svc.get_active_session)
_create_session = sync_to_async(chat_svc.create_session)
_close_session = sync_to_async(chat_svc.close_session)
_save_system_message = sync_to_async(chat_svc.save_system_message)
_can = sync_to_async(PermissionChecker.can)


def _refuse(personas: list, code: str, message: str) -> list[dict]:
    """The refusals payload for `personas`, one entry each (see MentionRefusalOut)."""
    return [{"persona_id": str(p.id), "name": p.name, "code": code, "message": message, "resets_at": None} for p in personas]


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

    # 5b. The right to call personas here. persona.mention is TOPIC-scoped, so
    #     one check covers every persona in this message. Refused ones are
    #     reported back to the sender (response + mention_refused event) and
    #     never reach the worker; the message itself already posted, only the
    #     AI reply is withheld. With no personas left, a "@X @session" from
    #     someone without the right opens no session either.
    refusals: list[dict] = []
    if mentioned_personas and not await _can(user, "persona.mention", obj=topic):
        refusals = _refuse(mentioned_personas, "no_right", "You can't call personas in this topic.")
        logger.warning("[chat/api] mention refused user=%s topic=%s personas=%s", user.id, topic_id, [p.name for p in mentioned_personas])
        mentioned_personas = []

    # 5c. A /routine token names a team method in this project -- if one answers
    #     to that name. If none does, the token was just a word: it stays in the
    #     message as typed and nobody is refused over it.
    routine = None
    if directives.routine_name:
        routine = await _get_routine_by_name(project, directives.routine_name)
    clean_message = directives.message_without_routine if routine else directives.clean_message

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
        if directives.message_without_mentions(clean_message):
            refusals = await _trigger_personas(mentioned_personas, company, project, topic,
                                                topic_id, msg, clean_message,
                                                directives.output_type, directives.swarm, routine, user) or refusals

    elif mentioned_personas:
        # Rule 3: @mentions (no @session) — trigger only mentioned, session unchanged
        refusals = await _trigger_personas(mentioned_personas, company, project, topic,
                                            topic_id, msg, clean_message,
                                            directives.output_type, directives.swarm, routine, user) or refusals

    else:
        # Rules 4 + 5: no explicit mention — check session
        active_session = await _get_active_session(user.id, topic.id)
        if active_session:
            # Rule 4: session active — trigger all session personas. The
            # right is re-checked: a session outlives a role change.
            session_personas = list(active_session.personas.all())
            if session_personas and not await _can(user, "persona.mention", obj=topic):
                refusals = _refuse(session_personas, "no_right", "You can't call personas in this topic.")
                logger.warning("[chat/api] session auto-trigger refused user=%s topic=%s", user.id, topic_id)
            else:
                logger.warning(
                    "[chat/api] session auto-trigger personas=%s",
                    [p.name for p in session_personas],
                )
                refusals = await _trigger_personas(session_personas, company, project, topic,
                                                    topic_id, msg, clean_message,
                                                    directives.output_type, directives.swarm, routine, user) or refusals
        # Rule 5: no mention, no session — human-only message, nothing to do

    if refusals:
        asyncio.create_task(chat_svc.publish_async(
            centrifugo_channel, mention_refused_event(msg["id"], str(user.id), refusals),
        ))

    # 7. Return immediately
    return {
        "message": msg,
        "channel": centrifugo_channel,
        "refusals": refusals,
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
    swarm: bool,
    routine=None,
    triggered_by=None,
) -> list[dict]:
    """
    Fire AI trigger tasks for each persona in parallel. Returns any refusals --
    personas that will not answer this message, and why.
    Spawns one asyncio task per persona. Only triggers personas that have
    a model configured -- a cheap existence check, not a judgment about the
    model's actual configuration, so it stays here. (The old source_type
    model/agent split is gone; see the gate in the loop below.)

    History is NOT built here anymore -- nexus-ai fetches and filters it
    itself, per persona, right before building that persona's prompt (see
    #131). This function's only job is deciding WHO to trigger.
    """
    if not personas:
        return []
    # Turn off swarm mode if only one persona is mentioned
    swarm = swarm and len(personas) > 1

    if swarm:
        # A gated persona proposes before it acts, and the swarm path has no plan
        # to approve — it used to run them with the gate simply ignored, so the
        # same persona was safe alone and not safe in company (audit, 2026-09-21).
        # One at a time is the honest answer until a swarm can carry a plan.
        gated = [p for p in personas if getattr(p, "acts_after_approval", False)]
        if gated:
            names = ", ".join(f"@{p.name}" for p in gated)
            logger.warning("[chat/api] swarm refused: gated personas %s", [p.name for p in gated])
            return _refuse(
                personas, "gated_in_swarm",
                f"{names} proposes a plan before acting, which a /swarm run cannot ask you to approve. "
                "Mention them on their own.",
            )
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
                triggered_by=triggered_by,
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
                    routine=routine,  # a swarm run ignores routines (documented)
                    triggered_by=triggered_by,
                )
            )
    return []


@router.post(
    "/{project_id}/channels/{channel_id}/topics/{topic_id}/messages/{message_id}/preflight/",
    response=PreflightDecisionOut,
)
async def decide_preflight(request, project_id: str, channel_id: str, topic_id: str, message_id: str, payload: PreflightDecisionIn):
    """
    Decide a persona's proposal (see chat/services.py decide_preflight). The
    right is persona.approve_run at the topic: whoever can talk to the persona
    here can approve what it proposes.
    """
    _company, user, _project, _channel, topic = await _resolve_topic(request, project_id, channel_id, topic_id)
    try:
        return await chat_svc.decide_preflight(topic=topic, message_id=message_id, user=user, decision=payload.decision, note=payload.note)
    except chat_svc.PreflightError as exc:
        raise HttpError(exc.status, str(exc))


@router.post(
    "/{project_id}/channels/{channel_id}/topics/{topic_id}/messages/{message_id}/approvals/{call_id}/",
    response=ToolApprovalDecisionOut,
)
async def decide_tool_approval(request, project_id: str, channel_id: str, topic_id: str, message_id: str, call_id: str, payload: ToolApprovalDecisionIn):
    """
    Allow or deny a tool call a persona holds for approval (chat/services.py
    decide_tool_approval): persona.approve_run at the topic, plus
    persona.update on the project when `always` changes the persona.
    """
    _company, user, _project, _channel, topic = await _resolve_topic(request, project_id, channel_id, topic_id)
    try:
        return await chat_svc.decide_tool_approval(topic=topic, message_id=message_id, call_id=call_id, user=user, decision=payload.decision, always=payload.always)
    except chat_svc.ApprovalError as exc:
        raise HttpError(exc.status, str(exc))


@router.post(
    "/{project_id}/channels/{channel_id}/topics/{topic_id}/messages/{message_id}/stop/",
    response=StopMessageOut,
)
async def stop_message(request, project_id: str, channel_id: str, topic_id: str, message_id: str):
    """
    End a persona reply that is still streaming. The reply is its caller's to
    stop (W22, the owner's rule); a reply from before the caller was recorded
    keeps the earlier rule -- anyone who can read the topic. The relay keeps
    what has streamed so far and marks the message stopped; the reader sees
    the effect on the bubble itself, not in a toast.
    """
    from .stop_signals import stop_signals

    _company, user, _project, _channel, topic = await _resolve_topic(
        request, project_id, channel_id, topic_id
    )
    outcome = await sync_to_async(chat_svc.request_stop_for_message)(topic, message_id, user)
    if outcome == "not_found":
        raise HttpError(404, "Message not found.")
    if outcome == "not_owner":
        raise HttpError(403, "Only the person who called the persona can stop this reply.")
    if outcome == "finished":
        raise HttpError(409, "This reply has already finished.")
    if outcome == "orphaned":
        # No relay is running this reply (nucleus restarted mid-run). It has
        # just been failed with that reason; tell everyone in the topic.
        from .events import message_error_event
        from .reasons import ORPHANED_RUN_REASON
        await chat_svc.publish_async(chat_svc.topic_channel(topic_id), message_error_event(message_id, ORPHANED_RUN_REASON))
        return {"stopping": True}
    await stop_signals().request_stop(message_id)
    # A live relay ends the reply within seconds of the signal. If nothing has
    # by the grace, no relay is there, and this ends it -- a stop must always
    # end something (2026-09-22, the deployed server).
    asyncio.create_task(chat_svc.end_if_still_pending(topic_id, message_id))
    return {"stopping": True}


@search_router.get("/messages/", response=List[MessageSearchOut])
async def search_messages(request, q: str, limit: int = 20):
    """
    Find a message across every chat this person can see (W19).

    The worker ranks by meaning; this filters by what the person may see and
    builds each result from our own rows. When the worker cannot answer, the
    same visible messages are searched literally instead of failing.
    """
    from chat import search as search_svc

    user = request.auth
    query = (q or "").strip()[:search_svc.QUERY_MAX]
    if not query:
        return []
    limit = max(1, min(int(limit or 20), search_svc.RESULTS_MAX))
    company = await sync_to_async(ws_svc.get_company)()
    if not company:
        raise HttpError(503, "Server not initialised.")

    topic_ids = await sync_to_async(search_svc.visible_topic_ids)(user, company)
    if not topic_ids:
        return []
    project_ids = await sync_to_async(lambda: [str(p.id) for p in ws_svc.list_projects(company, user)])()

    try:
        ranked = await search_svc.semantic_ids(company, query, project_ids, limit)
    except Exception:  # noqa: BLE001 -- a search box must never answer with a 500
        logger.warning("[search] the ranking step failed; searching the rows instead", exc_info=True)
        ranked = []
    if ranked:
        rows = await sync_to_async(lambda: list(search_svc._rows(ranked, topic_ids)))()
        ordered = search_svc.order_by(ranked, rows)
        if ordered:
            return [search_svc._result(m, query) for m in ordered[:limit]]
    # Nothing from the worker, or nothing of it visible: search the rows directly.
    rows = await sync_to_async(search_svc.literal)(query, topic_ids, limit)
    return [search_svc._result(m, query) for m in rows]


@router.post(
    "/{project_id}/channels/{channel_id}/topics/{topic_id}/messages/{message_id}/nudge/",
    response={200: dict},
)
async def nudge_message(request, project_id: str, channel_id: str, topic_id: str, message_id: str, payload: NudgeIn):
    """
    Add to a persona reply that is still running (W8 Nudge): the worker takes
    it at the persona's next step; one it never reaches is posted as a
    message when the reply ends. The reply is its caller's to steer.
    """
    from .stop_signals import stop_signals

    _company, user, _project, _channel, topic = await _resolve_topic(request, project_id, channel_id, topic_id)
    outcome = await sync_to_async(chat_svc.request_nudge_for_message)(topic, message_id, user)
    if outcome == "not_found":
        raise HttpError(404, "Message not found.")
    if outcome == "not_owner":
        raise HttpError(403, "Only the person who called the persona can nudge this reply.")
    if outcome == "finished":
        raise HttpError(409, "This reply has already finished.")
    await stop_signals().add_nudge(message_id, {"text": payload.text, "user_id": str(user.id), "name": user.display_name or user.username})
    return {"queued": True}
