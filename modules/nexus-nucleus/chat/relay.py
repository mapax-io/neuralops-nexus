"""
The relay — one persona reply's whole life (Step 2, docs/NUCLEUS-REVAMP.md).

nucleus's job here is orchestration only: create the placeholder message,
hand the engine a TriggerJob, relay the stream to the topic's channel, save
the result. The engine resolves persona/model/history itself (its
nucleus_client.py calls back into /internal/).

What the new relay does that the old one could not:
  - speaks the new engine's whole event language (question_asked,
    message_paused, deep_escalation, context_retrieved, keepalive) — the
    engine's 106 tests define it (fastapi_app/contracts/trigger.py)
  - queue per topic: two triggers on one topic run in order, never
    interleaved (a schedule firing mid-chat waits its turn)
  - pause-and-resume: message_paused parks the reply (status PAUSED); the
    engine POSTed its state to /internal/messages/{msg}/pause/ first; a
    resume re-sends the SAME job plus the decisions (chat/approvals.py)
  - real statuses: PENDING → STREAMING → COMPLETED/FAILED/CANCELLED/PAUSED

Errors are logged and swallowed — AI failure must never affect chat.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone as dt_timezone

from asgiref.sync import sync_to_async

from .approvals import parse_plan, record_approval_request, record_question
from .events import tool_activity_end_event, tool_activity_event, tool_approval_event
from .messages import (
    build_context_sources,
    create_ai_message,
    fail_ai_message,
    remember_tool_call,
    repost_untaken_nudges,
    set_message_status,
    update_ai_message,
    usage_from,
    with_usage,
)
from .nexus_ai import NexusAIClient
from .realtime import publish_async, topic_channel
from .reasons import explain_ai_error
from .stop_signals import StopRequested, stop_signals

logger = logging.getLogger(__name__)

# ── Queue per topic ───────────────────────────────────────────────────────────
# One in-process lock per topic: replies acquire it in arrival order, so two
# triggers on one topic stream one after the other. In-process is enough —
# one nucleus process owns the relays it started (fire-and-forget tasks).
#
# The lock is kept PER EVENT LOOP (same reason as RedisStore's client): a
# Celery worker reaches this through async_to_sync (a schedule's fire, pause
# expiry), which opens a FRESH loop per call — and an asyncio.Lock binds to
# the loop that first acquires it, so reusing one across loops raises
# "bound to a different event loop". A stale-loop lock is dropped, never
# awaited: its loop is already gone, nothing can still be holding it.
_topic_locks: dict[str, tuple[object, asyncio.Lock]] = {}


def _lock_for(topic_id: str) -> asyncio.Lock:
    loop = asyncio.get_running_loop()
    entry = _topic_locks.get(topic_id)
    if entry is None or entry[0] is not loop:
        entry = (loop, asyncio.Lock())
        _topic_locks[topic_id] = entry
    return entry[1]


async def end_stopped_reply(channel: str, msg_id: str, content: str, activity_trail: list | None = None, nudges: list[str] | None = None) -> None:
    """The reader stopped the run: keep what streamed, tell the topic, drop the signal."""
    try:
        await sync_to_async(update_ai_message)(msg_id, content, stopped=True, activity_trail=activity_trail, nudges=nudges)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[relay] failed to save stopped message %s: %s", msg_id, exc)
    await publish_async(channel, with_usage({
        "type": "message_done",
        "id": msg_id,
        "content": content,
        "output_type": "text",
        "render_as": "text",
        "stopped": True,  # the reader ended it; content is what streamed
    }, None))
    await stop_signals().clear(msg_id)


async def trigger_ai_response_async(
    *,
    company,
    project,
    topic,
    persona,
    user_message: str,
    user_message_id: str,
    topic_id: str,
    output_type: str = "auto",
    approved_plan: str | None = None,
    interactive: bool = True,
    routine=None,
    triggered_by=None,
    step_context: str | None = None,
    runbook_run: dict | None = None,
) -> str | None:
    """
    Fire-and-forget: one persona reply, start to finish. Returns the reply's
    message id (None when no reply row could be made) — a runbook (W6)
    awaits it and reads the row for the step's outcome.
    """
    client = NexusAIClient()
    if not client.configured:
        logger.warning("[relay] NEXUS_AI_URL not set — skipping AI response")
        return None

    # 1. Pre-create the reply row and show the bubble NOW — even when this
    #    reply has to wait its turn behind another one on the same topic.
    try:
        ai_msg = await sync_to_async(create_ai_message)(company, project, topic, persona, triggered_by=triggered_by, runbook_run=runbook_run)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[relay] failed to create AI message: %s", exc)
        return None

    msg_id = ai_msg["id"]
    channel = topic_channel(topic_id)
    await publish_async(channel, {
        "type": "message_start",
        "id": msg_id,
        "sender_id": ai_msg["sender_id"],
        "sender_name": ai_msg["sender_name"],
        "sender_avatar": ai_msg["sender_avatar"],  # #148
        "sequence": ai_msg["sequence"],
        "created_at": datetime.now(dt_timezone.utc).isoformat(),
        "triggered_by_id": ai_msg.get("triggered_by_id"),  # whose reply this is (W22)
        "triggered_by_name": ai_msg.get("triggered_by_name"),
        "runbook_run": ai_msg.get("runbook_run"),  # which runbook step this is (W6)
    })

    # 2. The job. Guarded context build: this runs unawaited, and a raise here
    #    used to leave a spinner with no terminal event (audit, 2026-09-21).
    try:
        context_sources = await sync_to_async(build_context_sources)(topic, company, persona)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[relay] context sources unavailable for msg %s: %s", msg_id, exc)
        context_sources = []

    job = {
        "job_id": str(uuid.uuid4()),
        "msg_id": msg_id,
        "persona_id": str(persona.id),
        "topic_id": topic_id,
        "user_message_id": user_message_id,
        "message": user_message,
        # O2: the three ids the engine stamps onto every usage record (Step 1).
        "company_id": str(company.id),
        "project_id": str(project.id),
        "user_id": str(triggered_by.id) if triggered_by is not None else "",
        "context_sources": context_sources,
        "output_type": output_type,
        # Preflight: a gated persona plans first when nobody has approved a plan
        # yet — only for interactive turns (a schedule has nobody to ask).
        "preflight": bool(interactive and persona.acts_after_approval and not approved_plan),
        "approved_plan": approved_plan,
        "interactive": bool(interactive),
        "routine_id": str(routine.id) if routine is not None else None,
        "step_context": step_context,
    }

    # 3. Stream — in topic order.
    async with _lock_for(topic_id):
        await _run_reply(
            client, job,
            msg_id=msg_id, channel=channel, company=company, project=project,
            topic=topic, topic_id=topic_id, ai_msg=ai_msg,
            user_message=user_message, user_message_id=user_message_id,
        )
    return msg_id


async def resume_paused_run(message_id: str) -> None:
    """
    Every pending call of a paused run is decided: re-send the ORIGINAL job
    plus the resume block (state + approvals + answers + the model seat).
    The engine continues the run on the same reply id; new deltas append to
    the same bubble.
    """
    from nucleus.models import ChatMessage, PausedRun

    run = await sync_to_async(lambda: PausedRun.objects.filter(message_id=message_id).first())()
    if not run:
        return
    msg = await sync_to_async(
        lambda: ChatMessage.objects.select_related("company", "project", "topic").filter(id=message_id).first()
    )()
    if not msg:
        await sync_to_async(lambda: PausedRun.objects.filter(message_id=message_id).delete())()
        return
    channel = topic_channel(str(msg.topic_id))
    job = dict(run.job or {})
    if not job:
        # The relay that started this run never recorded its job (nucleus
        # restarted between pause and now) — there is nothing to resume with.
        await sync_to_async(fail_ai_message)(message_id, "paused run lost its job across a restart",
                                             "This paused run can't be resumed — please ask again.")
        await publish_async(channel, {"type": "message_error", "id": message_id,
                                      "content": "This paused run can't be resumed — please ask again."})
        await sync_to_async(lambda: PausedRun.objects.filter(message_id=message_id).delete())()
        return

    approvals, answers = {}, {}
    for call_id, d in (run.decisions or {}).items():
        if d.get("kind") == "question":
            answers[call_id] = d.get("answer") or ""
        else:
            approvals[call_id] = {"decision": d.get("decision") or "deny", "reason": d.get("reason")}
    job["resume"] = {"state": run.state, "approvals": approvals, "answers": answers, "role": run.role or "STANDARD"}

    # The decisions are in the job now; the parked state is consumed.
    await sync_to_async(lambda: PausedRun.objects.filter(message_id=message_id).delete())()
    await sync_to_async(set_message_status)(message_id, ChatMessage.Status.STREAMING)

    client = NexusAIClient()
    async with _lock_for(str(msg.topic_id)):
        await _run_reply(
            client, job,
            msg_id=message_id, channel=channel, company=msg.company, project=msg.project,
            topic=msg.topic, topic_id=str(msg.topic_id), ai_msg=None,
            user_message=job.get("message") or "", user_message_id=job.get("user_message_id") or "",
        )


async def _run_reply(client, job, *, msg_id, channel, company, project, topic, topic_id, ai_msg, user_message, user_message_id) -> None:
    """One stream, start to terminal event. Shared by first runs and resumes."""
    from nucleus.models import ChatMessage, PausedRun

    streamed: list[str] = []
    final_output_type = "text"
    final_render_as = "text"
    final_clean_content: str | None = None
    embed_description: str | None = None
    ai_error: str | None = None
    ai_error_code: str | None = None
    usage: dict | None = None
    answered_by_model: str | None = None
    loaded_tools: list | None = None
    used_tools: list | None = None
    retrieved_sources: list | None = None
    nudges_taken: list[str] = []
    activity_trail: list = []
    stopped = False
    paused = False

    async def should_stop() -> bool:
        return await stop_signals().is_stop_requested(msg_id)

    await sync_to_async(set_message_status)(msg_id, ChatMessage.Status.STREAMING)

    try:
        async for event in client.stream_trigger(job, should_stop):
            event_type = event.get("type")

            if event_type in ("keepalive", "message_start"):
                # keepalive keeps the connection judged alive — the browser
                # never sees it; message_start was already published richer
                # (sender, avatar, sequence) when the row was made.
                continue

            if event_type == "message_delta":
                delta = event.get("delta") or ""
                if delta:
                    streamed.append(delta)
                    await publish_async(channel, {"type": "message_delta", "id": msg_id, "delta": delta})

            elif event_type == "tool_call_start":
                activity = tool_activity_event(msg_id, event)
                if activity:
                    await publish_async(channel, activity)

            elif event_type == "tool_call_end":
                ended = tool_activity_end_event(msg_id, event)
                if ended:
                    await publish_async(channel, ended)
                remember_tool_call(activity_trail, event)

            elif event_type == "nudge_taken":
                text = (event.get("nudge") or "").strip()
                if text:
                    nudges_taken.append(text)
                    await publish_async(channel, {"type": "nudge_taken", "id": msg_id, "text": text})

            elif event_type == "approval_requested":
                # The card shows NOW; the run will pause right after.
                record = await sync_to_async(record_approval_request)(msg_id, event.get("approval") or {})
                if record:
                    await publish_async(channel, tool_approval_event(msg_id, record))

            elif event_type == "question_asked":
                # Item 5: the model asked the person something (pauses too).
                record = await sync_to_async(record_question)(msg_id, event.get("question") or {})
                if record:
                    await publish_async(channel, {"type": "question_asked", "id": msg_id, "question": record})

            elif event_type == "context_retrieved":
                # Layer 3 decision 10: references and scores only, never chunks.
                await publish_async(channel, {
                    "type": "context_retrieved", "id": msg_id,
                    "retrieved": event.get("retrieved") or [],
                    "count": event.get("count") or len(event.get("retrieved") or []),
                })

            elif event_type == "deep_escalation":
                await publish_async(channel, {
                    "type": "deep_escalation", "id": msg_id,
                    "escalated_to": event.get("escalated_to"),
                })

            elif event_type == "message_paused":
                # Terminal for this stream. The engine POSTed its state to
                # /internal/messages/{msg}/pause/ BEFORE this event, so the
                # PausedRun row exists; give it the job so a decision can
                # rebuild the trigger.
                paused = True
                break

            elif event_type == "message_done":
                final_output_type = event.get("output_type") or "text"
                final_render_as = event.get("render_as") or "text"
                final_clean_content = event.get("content")
                embed_description = event.get("embed_description")
                usage = usage_from(event)
                answered_by_model = event.get("answered_by_model") or None
                loaded_tools = event.get("loaded_tools")
                used_tools = event.get("used_tools")
                retrieved_sources = event.get("retrieved_sources")
                break

            elif event_type == "message_error":
                ai_error = event.get("error") or "Unknown error"
                ai_error_code = event.get("error_code")
                logger.warning("[relay] engine reported error for msg %s: %s (code: %s)",
                               msg_id, ai_error, ai_error_code)
                break

    except StopRequested:
        stopped = True
    except Exception as exc:  # noqa: BLE001
        # Transport errors often carry no text (httpx.ReadError('')): the class
        # name is what says "connection", both in the log and to the categoriser.
        logger.warning("[relay] streaming error for msg %s: %s: %s", msg_id, type(exc).__name__, exc)
        ai_error = ai_error or f"streaming error: {type(exc).__name__}: {exc}"

    if stopped:
        await end_stopped_reply(channel, msg_id, "".join(streamed), activity_trail, nudges=nudges_taken)
        await repost_untaken_nudges(company, project, topic, msg_id, channel)
        return

    if paused:
        # Keep what streamed on the row, park the reply, hand the job to the
        # pause state so the decision road can resume it.
        def _park():
            PausedRun.objects.filter(message_id=msg_id).update(job=job)
            set_message_status(msg_id, ChatMessage.Status.PAUSED, content="".join(streamed))
        await sync_to_async(_park)()
        await publish_async(channel, {"type": "message_paused", "id": msg_id})
        return

    # The stream ended with neither message_done nor message_error: the engine
    # went away mid-reply. Saying so beats a bubble that goes quiet forever.
    if not ai_error and final_clean_content is None:
        ai_error = "worker ended the stream before it finished"

    save_content = final_clean_content if final_clean_content is not None else "".join(streamed)

    # A preflight reply is a proposal for a person to decide; one that is not
    # a plan at all is kept as ordinary text rather than a card with no plan.
    preflight = None
    if final_output_type == "preflight" and not ai_error:
        plan = parse_plan(save_content)
        if plan:
            preflight = {"status": "proposed", "plan": plan, "user_message": user_message, "user_message_id": user_message_id}
        else:
            final_output_type, final_render_as = "text", "text"

    recalled = len(retrieved_sources) if retrieved_sources else None

    # Terminal save + publish. The raw error stays server-side; the reader
    # sees the reauth prompt verbatim (written for them) or the categorised
    # sentence.
    display_error = (ai_error if ai_error_code == "mcp_reauth_required" else explain_ai_error(ai_error)) if ai_error else None
    try:
        if ai_error:
            await sync_to_async(fail_ai_message)(msg_id, ai_error, display_error, activity_trail)
        else:
            await sync_to_async(update_ai_message)(
                msg_id,
                save_content,
                render_as=final_render_as,
                output_type=final_output_type,
                usage=usage,
                activity_trail=activity_trail,
                preflight=preflight,
                answered_by_model=answered_by_model,
                recalled=recalled,
                nudges=nudges_taken,
                loaded_tools=loaded_tools,
                used_tools=used_tools,
                retrieved_sources=retrieved_sources,
                embed_description=embed_description,
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[relay] failed to update AI message %s: %s", msg_id, exc)

    await publish_async(channel, with_usage({
        "type": "message_error" if ai_error else "message_done",
        "id": msg_id,
        "content": display_error if ai_error else save_content,
        "output_type": final_output_type,
        "render_as": final_render_as,
        "stopped": False,
        "preflight": preflight,
        "answered_by_model": answered_by_model,
        "recalled": recalled or 0,
        "used_tools": used_tools or [],
        "retrieved_sources": retrieved_sources or [],
    }, usage))
    # A nudge the persona never reached is a message now, not a lost word.
    await repost_untaken_nudges(company, project, topic, msg_id, channel)

    # Embed — smart content selection: text/code full, html/form/terminal the
    # description only. Skipped on error — nothing real was generated.
    _TEXT_EMBEDDABLE = {"text", "code", "auto"}
    _DESC_EMBEDDABLE = {"html", "form", "terminal"}
    embed_content: str | None = None
    if not ai_error:
        if final_output_type in _TEXT_EMBEDDABLE and save_content:
            embed_content = save_content
        elif final_output_type in _DESC_EMBEDDABLE and embed_description:
            embed_content = embed_description

    if embed_content and ai_msg is not None:
        asyncio.create_task(client.embed_message({
            "message_id": msg_id,
            "company_id": str(company.id),
            "sequence": ai_msg["sequence"],
            "topic_id": topic_id,
            "channel_id": str(topic.channel_id),
            "project_id": str(project.id),
            "sender_id": ai_msg["sender_id"] or "",
            "sender_name": ai_msg["sender_name"] or "",
            "sender_type": "ai",
            "content": embed_content,
            "created_at": datetime.now(dt_timezone.utc).isoformat(),
            # Step 3 (changes 8 + 10.3): the tools that solved it ride as
            # vector metadata; the project's embedder spec picks the model.
            "used_tools": used_tools or [],
            "embedder": getattr(project, "embedder", None),
        }))
