"""
Chat services — save/load messages + publish to Centrifugo + embed to nexus-ai.

M7 additions:
  - extract_output_type(): parse @chart/@code/@terminal etc. from user message
  - trigger_ai_response_async(): passes output_type to nexus-ai TriggerJob
  - On message_done: captures output_type + render_as from nexus-ai event,
    publishes them to Centrifugo, stores render_as in message metadata
"""
from __future__ import annotations

import logging
import re
from datetime import timedelta
import asyncio

import httpx
from django.conf import settings
from django.db.models import Max
from django.utils import timezone
from asgiref.sync import sync_to_async
import json
import uuid
from datetime import datetime, timezone as dt_timezone
from authn.permissions.checker import PermissionChecker
from .events import preflight_decided_event, tool_activity_end_event, tool_activity_event, tool_approval_decided_event, tool_approval_event
from .stop_signals import StopRequested, stop_signals, stoppable, stoppable_lines
from .reasons import ORPHANED_RUN_REASON, WORKER_ENDED_EARLY_REASON, explain_ai_error

logger = logging.getLogger(__name__)

# ── M7: known output type keywords ────────────────────────────────────────────
# Must match the types registered in nexus-ai/apps/output_types/types.py
_OUTPUT_TYPE_KEYWORDS = frozenset({
    "text", "code", "html", "chart", "table", "diagram", "form", "terminal",
})

# Matches @keyword where keyword is a known output type (case-insensitive)
_OUTPUT_TYPE_RE = re.compile(
    r"@(" + "|".join(_OUTPUT_TYPE_KEYWORDS) + r")\b",
    re.IGNORECASE,
)


# ── M7.1: @session reserved keyword ──────────────────────────────────────────

# Matches "@session", "@session close", or "@session end" (case-insensitive)
_SESSION_RE = re.compile(r'@session(?:\s+(?:close|end))?\b', re.IGNORECASE)
_SESSION_CLOSE_RE = re.compile(r'@session\s+(?:close|end)\b', re.IGNORECASE)


# ── @mentions ─────────────────────────────────────────────────────────────────

# Matches @Word — finds ALL @mentions in a message.
_MENTION_RE = re.compile(r'@([\w]+)')

# Reserved keywords that are never persona names — everything else this
# module already parses as its own directive (@session/@session close,
# plus every output-type keyword above).
_RESERVED_MENTIONS = frozenset({"session", "close"}) | _OUTPUT_TYPE_KEYWORDS


def extract_session_directive(message: str) -> tuple[bool, bool, str]:
    """
    Detect @session / @session close / @session end in the user message.

    Returns:
        (has_session_open, is_close, clean_message)

        has_session_open — True if "@session" present (but not a close variant)
        is_close         — True if "@session close" or "@session end" present
        clean_message    — message with the @session directive stripped

    Examples:
        "@NeuralOps explain this @session"
            → (True, False, "@NeuralOps explain this")
        "@session close" or "@session end"
            → (False, True, "")
        "what is the weather"
            → (False, False, "what is the weather")
    """
    is_close = bool(_SESSION_CLOSE_RE.search(message))
    has_session = bool(_SESSION_RE.search(message)) and not is_close

    # Strip ALL @session / @session close occurrences from message
    clean = _SESSION_RE.sub("", message).strip()
    return has_session, is_close, clean


# ── M7.1: session DB helpers ──────────────────────────────────────────────────

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
                # agent__model / agent__mcp_server are gone with AIAgent. A
                # persona now IS the composition: one ModelConfig, optionally
                # an advisor, and an mcp_servers M2M (prefetched, not
                # select_related -- it is many-to-many).
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

    If a session already exists it is closed first, then a new one is created.
    personas is a list of Persona model instances.
    Returns the new ChatSession.
    """
    from nucleus.models import ChatSession

    # Close any existing session first
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
    Close the active session for this user+topic.
    Sessions are ephemeral state — hard-deleted, not soft-deleted,
    so the unique (user, topic) constraint stays clean for re-opens.
    Returns the closed session's persona names (possibly empty), or None if
    no session existed — so the caller can name them in the system message.
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


def extract_output_type(message: str) -> tuple[str, str]:
    """
    Detect @output_type directives in the user message.

    Returns:
        (output_type, clean_message)

    If no directive found, returns ("auto", original_message).
    If found, the directive is stripped from the message before it's sent to the AI.

    Examples:
        "Show me sales @chart for Q4"
            → ("chart", "Show me sales  for Q4")
        "@Nova explain the code @code"
            → ("code", "@Nova explain the code ")
        "@Nova explain the code"
            → ("auto", "@Nova explain the code")
    """
    m = _OUTPUT_TYPE_RE.search(message)
    if not m:
        return "auto", message

    output_type = m.group(1).lower()
    # Strip the @directive from the message text sent to the LLM
    clean = message[:m.start()] + message[m.end():]
    return output_type, clean.strip()


# ── Every @directive, parsed once, up front ─────────────────────────────────

# A routine token: the FIRST standalone /name (lowercase letters, digits,
# hyphens) -- "/etc/hosts" and "50/50" are not, and /swarm was stripped first.
_ROUTINE_RE = re.compile(r"(?:(?<=\s)|^)/([a-z0-9-]+)(?=\s|$)")


def extract_routine(message: str) -> tuple[str | None, str]:
    """(routine name, message without that token) -- one token, the first; the rest of the text is untouched."""
    m = _ROUTINE_RE.search(message)
    if not m:
        return None, message
    before, after = message[: m.start()], message[m.end():]
    # Only the token and one of the spaces around it go; the rest of the text stays as typed.
    if before.endswith(" ") and after.startswith(" "):
        after = after[1:]
    return m.group(1), (before + after).strip()


class MessageDirectives:
    """
    Every @directive a chat message can contain, parsed once, in one
    place. chat/api.py:send_message() reads the fields below to decide
    what to do -- it never parses text itself. This is what used to be
    a handful of separate extraction calls (extract_session_directive,
    extract_output_type, a regex for @mentions) interleaved with the
    actual dispatch logic; now "understand what the user typed" and
    "act on it" are two separate, easy-to-follow steps.

    Directives, checked/stripped in this order:
        /swarm              -- trigger the mentioned persona in swarm mode
        @session            -- open a session with whoever gets @mentioned
        @session close/end  -- close the active session, no AI trigger
        @output_type        -- e.g. @chart, @html -- how the AI should
                                format its reply
        /routine-name       -- the first standalone /token (W4 Routines);
                                resolved against the topic's project by
                                send_message
        @PersonaName         -- one or more persona mentions (anything
                                left over that isn't a reserved keyword)

    Usage:
        directives = MessageDirectives(payload.content.strip())
        if directives.is_session_close:
            ...
        elif directives.has_mentions and directives.has_session_open:
            ...
    """

    def __init__(self, raw: str):
        self.raw = raw

        self.swarm = "/swarm" in raw
        raw = re.sub(r'\s*/swarm\s*', ' ', raw).strip() if self.swarm else raw
        self.has_session_open, self.is_session_close, after_session = extract_session_directive(raw)
        self.output_type, self.clean_message = extract_output_type(after_session)
        # /routine-name -- resolved by send_message in the topic's project.
        self.routine_name, self.clean_message = extract_routine(self.clean_message)

        names = _MENTION_RE.findall(self.clean_message)
        self.mention_names = [n for n in names if n.lower() not in _RESERVED_MENTIONS]

    @property
    def has_mentions(self) -> bool:
        return bool(self.mention_names)

    def message_without_mentions(self) -> str:
        """clean_message with every @mention stripped too -- used to check
        whether there's any actual content left to send to the AI once
        the @PersonaName addressing is removed."""
        return _MENTION_RE.sub("", self.clean_message).strip()


# ── Centrifugo publish ─────────────────────────────────────────────────────────

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


# ── Embed fire-and-forget (nexus-ai) ──────────────────────────────────────────

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


# ── AI trigger — fire-and-forget (M3 + M7) ────────────────────────────────────

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
    return _serialise(msg)


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
    recalled: int | None = None,
    nudges: list[str] | None = None,
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
    if recalled:
        metadata["recalled"] = recalled
    if nudges:
        metadata["nudges"] = list(nudges)
    if preflight:
        metadata["preflight"] = preflight

    ChatMessage.objects.filter(id=message_id).update(
        content=content,
        status=ChatMessage.Status.COMPLETED,
        metadata=metadata,
    )


def fail_ai_message(message_id: str, error: str, display_content: str | None = None, activity_trail: list | None = None) -> None:
    """
    Mark the AI placeholder message FAILED instead of COMPLETED -- called
    when nexus-ai reports an AgentEvent(type="message_error") (see
    apps/routers/trigger.py on the nexus-ai side). Without this, a failed
    trigger used to fall through to update_ai_message() anyway and land
    on "completed" with blank content -- indistinguishable from the AI
    genuinely replying with nothing.

    display_content overrides the generic placeholder -- used for errors
    the user should actually see verbatim (e.g. mcp_reauth_required). The
    real error is always kept in metadata.error_detail for debugging either way.
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


USAGE_FIELDS = ("prompt_tokens", "output_tokens", "context_window")
# How many closed tool calls a reply keeps on its row: enough to audit a
# long agentic run, small enough to ride in the message metadata.
ACTIVITY_TRAIL_MAX = 50


PLAN_MAX_STEPS = 12


def parse_plan(content: str) -> dict | None:
    """The plan a preflight reply carries, or None when the content is not one."""
    try:
        raw = json.loads(content)
    except (TypeError, ValueError):
        return None
    if not isinstance(raw, dict) or not isinstance(raw.get("steps"), list):
        return None
    steps = []
    for step in raw["steps"][:PLAN_MAX_STEPS]:
        if not isinstance(step, dict) or not str(step.get("title", "")).strip():
            continue
        tools = step.get("tools") if isinstance(step.get("tools"), list) else []
        steps.append({"title": str(step["title"]).strip(), "tools": [str(t) for t in tools], "writes": bool(step.get("writes"))})
    risks = [str(r) for r in raw["risks"]] if isinstance(raw.get("risks"), list) else []
    return {"summary": str(raw.get("summary") or "").strip(), "steps": steps, "risks": risks}


def plan_text(plan: dict) -> str:
    """The approved plan as the worker puts it ahead of the persona prompt."""
    lines = [plan["summary"]] if plan.get("summary") else []
    for i, step in enumerate(plan.get("steps", []), 1):
        detail = ", ".join(step.get("tools") or [])
        lines.append(f"{i}. {step['title']}" + (f" (tools: {detail})" if detail else "") + (" (writes)" if step.get("writes") else ""))
    return "\n".join(lines)


class PreflightError(Exception):
    """A decision that cannot be applied; `status` is the HTTP answer."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def _message_in_topic(topic, message_id):
    """The row for a message id in this topic, or None -- also for an id that is not a UUID (a scheduled fire's)."""
    from nucleus.models import ChatMessage
    try:
        uuid.UUID(str(message_id))
    except (ValueError, TypeError):
        return None
    return ChatMessage.objects.select_related("sender").filter(id=message_id, topic=topic).first()


async def decide_preflight(*, topic, message_id: str, user, decision: str, note: str | None = None) -> dict:
    """
    Approve, adjust or decline a persona's proposal. Approve runs the plan with
    the tools back on; adjust asks for another plan with the note; decline ends
    it with a line in the topic. Once decided, a proposal stays decided.
    """
    from nucleus.models import ChatMessage, Persona

    if decision not in ("approve", "adjust", "decline"):
        raise PreflightError(400, "Decision must be approve, adjust or decline.")
    msg = await sync_to_async(lambda: ChatMessage.objects.select_related("project", "company").filter(id=message_id, topic=topic).first())()
    if not msg:
        raise PreflightError(404, "Message not found.")
    preflight = dict((msg.metadata or {}).get("preflight") or {})
    if preflight.get("status") != "proposed":
        raise PreflightError(409, "This plan has already been decided." if preflight else "This message carries no plan to decide.")
    if not await sync_to_async(PermissionChecker.can)(user, "persona.approve_run", obj=topic):
        raise PreflightError(403, "You don't have permission to decide a persona's plan here.")
    persona = await sync_to_async(lambda: Persona.objects.filter(id=(msg.metadata or {}).get("persona_id"), is_active=True).first())()
    if not persona:
        raise PreflightError(409, "The persona behind this plan is gone.")
    if decision == "adjust" and not (note or "").strip():
        raise PreflightError(400, "Say what to change.")

    status = {"approve": "approved", "adjust": "adjusted", "decline": "declined"}[decision]
    preflight.update({
        "status": status,
        "decided_by_id": str(user.id),
        "decided_by_name": user.get_display_name(),
        "decided_at": timezone.now().isoformat(),
        "note": (note or "").strip() or None,
    })
    metadata = dict(msg.metadata or {})
    metadata["preflight"] = preflight
    await sync_to_async(ChatMessage.objects.filter(id=msg.id).update)(metadata=metadata)
    channel = topic_channel(str(topic.id))
    await publish_async(channel, preflight_decided_event(str(msg.id), preflight))

    # The run is the asker's (W22): the sender of the message that asked, or the
    # decider when that message cannot be found.
    asked = await sync_to_async(_message_in_topic)(topic, preflight.get("user_message_id"))
    common = dict(company=msg.company, project=msg.project, topic=topic, persona=persona, topic_id=str(topic.id),
                  user_message_id=preflight.get("user_message_id") or "", output_type="auto",
                  triggered_by=(asked.sender if asked and asked.sender else user))
    if decision == "approve":
        asyncio.create_task(trigger_ai_response_async(user_message=preflight.get("user_message") or "", approved_plan=plan_text(preflight["plan"]), **common))
    elif decision == "adjust":
        asyncio.create_task(trigger_ai_response_async(user_message=note.strip(), **common))
    else:
        line = await sync_to_async(save_system_message)(msg.company, msg.project, topic, f"@{persona.name}'s plan was declined by {user.get_display_name()}.")
        await publish_async(channel, line)
    return {"status": status, "preflight": preflight}


# ── Tool approvals (W16) ──────────────────────────────────────────────────────
# A tool call the worker holds for a person lives on the reply row under
# metadata.approvals -- stored the moment the worker asks (it polls nucleus
# for the answer while the run stays open), decided under persona.approve_run
# at the topic, and expired with the reply if nobody answered in time.
APPROVALS_MAX = 20
APPROVAL_PREVIEW_CHARS = 300


class ApprovalError(Exception):
    """A decision that cannot be applied; `status` is the HTTP answer."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def approval_record(approval: dict) -> dict | None:
    """The row's record for a worker approval_requested payload; None when it names no call."""
    call_id = (approval.get("call_id") or "").strip()
    tool = (approval.get("tool") or "").strip()
    if not call_id or not tool:
        return None
    return {
        "call_id": call_id,
        "tool": tool,
        "capability_id": (approval.get("capability_id") or "").strip(),
        "args_preview": (approval.get("args_preview") or "")[:APPROVAL_PREVIEW_CHARS],
        "status": "pending",
        "requested_at": timezone.now().isoformat(),
    }


def record_approval_request(message_id: str, approval: dict) -> dict | None:
    """Store a pending approval on the reply row NOW, mid-run, so the worker's poll can find it."""
    from nucleus.models import ChatMessage
    record = approval_record(approval)
    if not record:
        return None
    msg = ChatMessage.objects.filter(id=message_id).first()
    if not msg:
        return None
    metadata = dict(msg.metadata or {})
    approvals = [a for a in (metadata.get("approvals") or []) if a.get("call_id") != record["call_id"]]
    approvals.append(record)
    metadata["approvals"] = approvals[-APPROVALS_MAX:]
    ChatMessage.objects.filter(id=message_id).update(metadata=metadata)
    return record


def expire_open_approvals(metadata: dict) -> None:
    """A reply that ended leaves no call waiting: pending becomes expired, decisions stay."""
    approvals = metadata.get("approvals")
    if approvals:
        metadata["approvals"] = [{**a, "status": "expired"} if a.get("status") == "pending" else a for a in approvals]


async def approval_state(message_id: str, call_id: str) -> dict:
    """
    What the worker's poll is told: allowed / denied once someone decided,
    stopped once the reader ended the reply, pending otherwise -- including
    for a call the relay has not stored yet, which is a race, not an answer.
    """
    from nucleus.models import ChatMessage
    if await stop_signals().is_stop_requested(message_id):
        return {"status": "stopped", "always": False}
    msg = await sync_to_async(lambda: ChatMessage.objects.filter(id=message_id).only("metadata").first())()
    for record in ((msg.metadata or {}).get("approvals") or []) if msg else []:
        if record.get("call_id") == call_id and record.get("status") in ("allowed", "denied"):
            return {"status": record["status"], "always": bool(record.get("always"))}
    return {"status": "pending", "always": False}


async def decide_tool_approval(*, topic, message_id: str, call_id: str, user, decision: str, always: bool = False) -> dict:
    """
    Allow or deny a held tool call, under persona.approve_run at the topic.
    `always` also writes "<capability>/<tool>": "auto" onto the persona, which
    is persona configuration and so needs persona.update on the project too.
    Once decided, a call stays decided.
    """
    from nucleus.models import ChatMessage, Persona

    if decision not in ("allow", "deny"):
        raise ApprovalError(400, "Decision must be allow or deny.")
    msg = await sync_to_async(lambda: ChatMessage.objects.select_related("project").filter(id=message_id, topic=topic).first())()
    if not msg:
        raise ApprovalError(404, "Message not found.")
    metadata = dict(msg.metadata or {})
    approvals = list(metadata.get("approvals") or [])
    record = next((a for a in approvals if a.get("call_id") == call_id), None)
    if not record:
        raise ApprovalError(404, "This message holds no such tool call.")
    if record.get("status") != "pending":
        raise ApprovalError(409, "This call has already been decided.")
    if not await sync_to_async(PermissionChecker.can)(user, "persona.approve_run", obj=topic):
        raise ApprovalError(403, "You don't have permission to decide a persona's tool calls here.")
    if always and not await sync_to_async(PermissionChecker.can)(user, "persona.update", obj=msg.project):
        raise ApprovalError(403, "Allowing a tool always changes the persona, which needs the right to edit personas.")

    if always and decision == "allow":
        persona = await sync_to_async(lambda: Persona.objects.filter(id=metadata.get("persona_id"), is_active=True).first())()
        if persona:
            levels = dict(persona.tool_levels or {})
            levels[f"{record.get('capability_id') or ''}/{record['tool']}"] = "auto"
            persona.tool_levels = levels
            await sync_to_async(persona.save)(update_fields=["tool_levels"])

    record.update({
        "status": "allowed" if decision == "allow" else "denied",
        "always": bool(always and decision == "allow"),
        "decided_by_id": str(user.id),
        "decided_by_name": user.get_display_name(),
        "decided_at": timezone.now().isoformat(),
    })
    metadata["approvals"] = [record if a.get("call_id") == call_id else a for a in approvals]
    await sync_to_async(ChatMessage.objects.filter(id=msg.id).update)(metadata=metadata)
    await publish_async(topic_channel(str(topic.id)), tool_approval_decided_event(str(msg.id), record))
    return {"status": record["status"], "approval": record}


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


async def end_stopped_reply(channel: str, msg_id: str, content: str, activity_trail: list | None = None, nudges: list[str] | None = None) -> None:
    """The reader stopped the run: keep what streamed, tell the topic, drop the signal."""
    try:
        await sync_to_async(update_ai_message)(msg_id, content, stopped=True, activity_trail=activity_trail, nudges=nudges)
    except Exception as exc:
        logger.warning("[trigger] failed to save stopped message %s: %s", msg_id, exc)
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
    Fire-and-forget: trigger nexus-ai to generate a persona response.
    Returns the reply's message id (None when no reply row could be made) --
    a runbook (W6) awaits it and reads the row for the step's outcome.

    nexus-nucleus's job here is orchestration only -- create the placeholder
    message, tell nexus-ai which persona + topic + message to respond to,
    relay the stream, save the result. It does NOT resolve the persona's
    model/API key/system prompt, and does NOT fetch or filter conversation
    history -- nexus-ai pulls both of those itself, right before it builds
    the prompt (see nexus-ai: apps/managers/nucleus_client.py + agentic_manager.py).
    That's a deliberate move: how much history to include and which past
    replies are "good enough" to show the model are prompt-quality calls,
    not chat-orchestration ones.

    M7 additions:
    - Passes output_type to nexus-ai TriggerJob
    - Captures output_type + render_as from message_done event
    - Publishes both to Centrifugo on message_done
    - Stores render_as in ChatMessage.metadata for history replay

    Flow:
        1. Pre-create AI message in DB (status=PENDING)
        2. Publish message_start to Centrifugo
        3. Call nexus-ai POST /api/v1/trigger/ with a minimal job
           (job_id, msg_id, persona_id, topic_id, user_message_id, message,
           output_type) — SSE stream
        4. For each message_delta: publish token to Centrifugo
        5. On message_done: update DB message, publish message_done + output_type + render_as

    Errors are logged and swallowed — AI failure must never affect chat.
    """

    nexus_ai_url = getattr(settings, "NEXUS_AI_URL", "")
    internal_key = getattr(settings, "INTERNAL_API_KEY", "")

    if not nexus_ai_url:
        logger.warning("[trigger] NEXUS_AI_URL not set — skipping AI response")
        return

    # 1. Pre-create AI message in DB
    _create_ai_message = sync_to_async(create_ai_message)
    _update_ai_message = sync_to_async(update_ai_message)
    _fail_ai_message = sync_to_async(fail_ai_message)

    try:
        ai_msg = await _create_ai_message(company, project, topic, persona, triggered_by=triggered_by, runbook_run=runbook_run)
    except Exception as exc:
        logger.warning("[trigger] failed to create AI message: %s", exc)
        return None

    msg_id = ai_msg["id"]
    channel = topic_channel(topic_id)
    now = datetime.now(dt_timezone.utc).isoformat()

    # 2. Publish message_start
    await publish_async(channel, {
        "type": "message_start",
        "id": msg_id,
        "sender_id": ai_msg["sender_id"],
        "sender_name": ai_msg["sender_name"],
        "sender_avatar": ai_msg["sender_avatar"],  # #148 -- already in _serialise()'s dict
        "sequence": ai_msg["sequence"],
        "created_at": now,
        "triggered_by_id": ai_msg.get("triggered_by_id"),  # whose reply this is (W22)
        "triggered_by_name": ai_msg.get("triggered_by_name"),
        "runbook_run": ai_msg.get("runbook_run"),  # which runbook step this is (W6)
    })

    # 3. Build the minimal TriggerJob payload -- nexus-ai resolves persona/
    #    model config and history itself via its own internal calls back
    #    into nucleus (see nucleus_client.py). context_sources is the one
    #    exception, still built and pushed here for now -- there's an
    #    existing but UNVERIFIED nexus-ai-side endpoint for topic contexts
    #    that queries a different model (TopicContext) than this function
    #    actually uses (ContextSource); switching to it without confirming
    #    they're equivalent risks silently breaking RAG/attached-file search.
    #    Left as a separate, explicitly flagged follow-up -- see #131.

    # _build_context_sources does sync ORM queries — must be wrapped for async context
    context_sources = await sync_to_async(_build_context_sources)(topic, company, persona)

    job_payload = {
        "job_id": str(uuid.uuid4()),
        "msg_id": msg_id,
        "persona_id": str(persona.id),
        "topic_id": topic_id,
        "user_message_id": user_message_id,
        "message": user_message,
        "context_sources": context_sources,
        "output_type": output_type,  # M7: "auto" | "chart" | "code" | "terminal" | ...
        # Preflight: a gated persona plans first when nobody has approved a plan
        # yet -- only for interactive turns (a schedule has nobody to ask).
        "preflight": bool(interactive and persona.acts_after_approval and not approved_plan),
        "approved_plan": approved_plan,
        # Tool approvals: an Ask tool may wait for a person only when one is
        # watching (a chat turn); a schedule refuses it at once.
        "interactive": bool(interactive),
        # Routines (W4): the team method this reply runs with; the worker
        # fetches it and applies its instructions, tool narrowing and model.
        "routine_id": str(routine.id) if routine is not None else None,
        # Runbooks (W6): the previous step's reply, for this step to build on.
        "step_context": step_context,
    }

    # 4. Stream from nexus-ai, relay tokens to Centrifugo
    streamed_content: list[str] = []
    final_output_type = "text"
    final_render_as = "text"
    final_clean_content: str | None = None
    embed_description: str | None = None
    ai_error: str | None = None
    ai_error_code: str | None = None
    usage: dict | None = None
    answered_by_model: str | None = None
    recalled: int | None = None
    nudges_taken: list[str] = []
    activity_trail: list = []
    stopped = False

    async def should_stop() -> bool:
        return await stop_signals().is_stop_requested(msg_id)

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            request = client.build_request(
                "POST",
                f"{nexus_ai_url}/api/v1/trigger/",
                json=job_payload,
                headers={
                    "X-Internal-Key": internal_key,
                    "Content-Type": "application/json",
                },
            )
            # The worker does its own setup before the first byte comes back;
            # a Stop must land during that wait too, not only once lines flow.
            response = await stoppable(client.send(request, stream=True), should_stop)
            try:
                if response.status_code != 200:
                    body = await response.aread()
                    raise RuntimeError(
                        f"nexus-ai /trigger/ returned {response.status_code}: {body.decode()[:300]}"
                    )

                # The reader may click Stop at any moment, including while the
                # worker is silent; leaving the stream closes the connection,
                # which cancels the worker's generator and its model call.
                async for line in stoppable_lines(response.aiter_lines(), should_stop):
                    if not line.startswith("data: "):
                        continue
                    raw = line[6:].strip()
                    if not raw:
                        continue
                    try:
                        event = json.loads(raw)
                        event_type = event.get("type")

                        if event_type == "tool_call_start":
                            # The worker has always emitted this; nucleus used to
                            # drop it, so a persona reaching for a tool looked
                            # like a stall. See docs/OPEN-ITEMS.md.
                            activity = tool_activity_event(msg_id, event)
                            if activity:
                                await publish_async(channel, activity)

                        elif event_type == "tool_call_end":
                            # How the call went -- closes the row above and is
                            # kept on the message so history shows the trail.
                            ended = tool_activity_end_event(msg_id, event)
                            if ended:
                                await publish_async(channel, ended)
                            remember_tool_call(activity_trail, event)

                        elif event_type == "nudge_taken":
                            # The caller added to the running reply and the
                            # persona took it at its next step (W8).
                            text = (event.get("nudge") or "").strip()
                            if text:
                                nudges_taken.append(text)
                                await publish_async(channel, {"type": "nudge_taken", "id": msg_id, "text": text})

                        elif event_type == "approval_requested":
                            # The worker holds a tool call for a person and
                            # polls for the answer: store it now, tell the topic.
                            record = await sync_to_async(record_approval_request)(msg_id, event.get("approval") or {})
                            if record:
                                await publish_async(channel, tool_approval_event(msg_id, record))

                        elif event_type == "message_delta":
                            delta = event.get("delta") or ""
                            if delta:
                                streamed_content.append(delta)
                                await publish_async(channel, {
                                    "type": "message_delta",
                                    "id": msg_id,
                                    "delta": delta,
                                })

                        elif event_type == "message_done":
                            # M7: capture resolved output type from nexus-ai
                            final_output_type = event.get("output_type") or "text"
                            final_render_as = event.get("render_as") or "text"
                            # Use nexus-ai's clean content (markers stripped)
                            final_clean_content = event.get("content")
                            # M8: plain-text description for html/form/terminal embedding
                            embed_description = event.get("embed_description")
                            usage = usage_from(event)
                            # "<model> (fallback)" when the persona's own model could not answer.
                            answered_by_model = event.get("answered_by_model") or None
                            # How many entries the reply recorded in the project's Recall (W5).
                            recalled = int(event.get("recalled") or 0) or None
                            break

                        elif event_type == "message_error":
                            # nexus-ai's pipeline raised before/during generation --
                            # see apps/routers/trigger.py:_event_stream on that side.
                            ai_error = event.get("error") or "Unknown error"
                            ai_error_code = event.get("error_code")  # NEW
                            logger.warning(
                                "[trigger] nexus-ai reported error for msg %s: %s (code: %s)",
                                msg_id, ai_error, ai_error_code,
                            )
                            break

                    except (json.JSONDecodeError, KeyError):
                        continue
            finally:
                await response.aclose()

    except StopRequested:
        stopped = True
    except Exception as exc:
        # Transport errors often carry no text (httpx.ReadError('')): the class
        # name is what says "connection", both in the log and to the categoriser.
        logger.warning("[trigger] streaming error for msg %s: %s: %s", msg_id, type(exc).__name__, exc)
        ai_error = ai_error or f"streaming error: {type(exc).__name__}: {exc}"

    if stopped:
        await end_stopped_reply(channel, msg_id, "".join(streamed_content), activity_trail, nudges=nudges_taken)
        await repost_untaken_nudges(company, project, topic, msg_id, channel)
        return msg_id  # nothing complete to embed

    # The stream ended with neither message_done nor message_error: the worker
    # went away mid-reply. Saying so beats a bubble that goes quiet forever.
    if not ai_error and final_clean_content is None:
        ai_error = "worker ended the stream before it finished"

    # Use nexus-ai's clean content if available, else fall back to streamed
    save_content = (
        final_clean_content
        if final_clean_content is not None
        else "".join(streamed_content)
    )

    # A preflight reply is a proposal for a person to decide; one that is not
    # a plan at all is kept as ordinary text rather than a card with no plan.
    preflight = None
    if final_output_type == "preflight" and not ai_error:
        plan = parse_plan(save_content)
        if plan:
            preflight = {"status": "proposed", "plan": plan, "user_message": user_message, "user_message_id": user_message_id}
        else:
            final_output_type, final_render_as = "text", "text"

    # 5. Save full content to DB + publish message_done (or FAILED + message_error)
    # What the reader sees: the reauth prompt verbatim (it is written for
    # them), otherwise the categorised sentence — never the raw error.
    display_error = (ai_error if ai_error_code == "mcp_reauth_required" else explain_ai_error(ai_error)) if ai_error else None
    try:
        if ai_error:
            await _fail_ai_message(msg_id, ai_error, display_error, activity_trail)
        else:
            await _update_ai_message(
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
            )
    except Exception as exc:
        logger.warning("[trigger] failed to update AI message %s: %s", msg_id, exc)

    await publish_async(channel, with_usage({
        "type": "message_error" if ai_error else "message_done",
        "id": msg_id,
        # Same friendly copy as fail_ai_message()'s DB write -- the raw
        # exception text (ai_error) stays server-side only (logged above +
        # stored in ChatMessage.metadata.error_detail), never shipped to
        # the browser over Centrifugo.
            "content": display_error if ai_error else save_content,
        "output_type": final_output_type,   # M7: e.g. "chart"
        "render_as": final_render_as,        # M7: e.g. "html"
        "stopped": False,                    # a stopped run ends in end_stopped_reply()
        "preflight": preflight,              # the proposal, so the card can be decided without a reload
        "answered_by_model": answered_by_model,
        "recalled": recalled or 0,
    }, usage))
    # A nudge the persona never reached is a message now, not a lost word.
    await repost_untaken_nudges(company, project, topic, msg_id, channel)

    # M8: Embed AI response — smart content selection
    # text/code → embed full response; html/form/terminal → embed description only
    # Skipped entirely on error -- nothing real was generated to embed.
    _TEXT_EMBEDDABLE = {"text", "code", "auto"}
    _DESC_EMBEDDABLE = {"html", "form", "terminal"}
    embed_content: str | None = None
    if not ai_error:
        if final_output_type in _TEXT_EMBEDDABLE and save_content:
            embed_content = save_content
        elif final_output_type in _DESC_EMBEDDABLE and embed_description:
            embed_content = embed_description

    if embed_content:
        asyncio.create_task(embed_message_async(
            message_id=msg_id,
            company_id=str(company.id),
            sequence=ai_msg["sequence"],
            topic_id=topic_id,
            channel_id=str(topic.channel_id),
            project_id=str(project.id),
            sender_id=ai_msg["sender_id"] or "",
            sender_name=ai_msg["sender_name"] or "",
            sender_type="ai",
            content=embed_content,
            created_at=now,
        ))
    return msg_id

async def trigger_ai_swarm_response_async(
    *,
    company,
    project,
    topic,
    personas,
    user_message: str,
    user_message_id: str,
    topic_id: str,
    output_type: str = "auto",
    triggered_by=None,
) -> None:
    """
    Fire-and-forget: trigger nexus-ai to generate a persona response.

    nexus-nucleus's job here is orchestration only -- create the placeholder
    message, tell nexus-ai which persona + topic + message to respond to,
    relay the stream, save the result. It does NOT resolve the persona's
    model/API key/system prompt, and does NOT fetch or filter conversation
    history -- nexus-ai pulls both of those itself, right before it builds
    the prompt (see nexus-ai: apps/managers/nucleus_client.py + agentic_manager.py).
    That's a deliberate move: how much history to include and which past
    replies are "good enough" to show the model are prompt-quality calls,
    not chat-orchestration ones.

    M7 additions:
    - Passes output_type to nexus-ai TriggerJob
    - Captures output_type + render_as from message_done event
    - Publishes both to Centrifugo on message_done
    - Stores render_as in ChatMessage.metadata for history replay

    Flow:
        1. Pre-create AI message in DB (status=PENDING)
        2. Publish message_start to Centrifugo
        3. Call nexus-ai POST /api/v1/trigger/ with a minimal job
           (job_id, msg_id, persona_id, topic_id, user_message_id, message,
           output_type) — SSE stream
        4. For each message_delta: publish token to Centrifugo
        5. On message_done: update DB message, publish message_done + output_type + render_as

    Errors are logged and swallowed — AI failure must never affect chat.
    """

    nexus_ai_url = getattr(settings, "NEXUS_AI_URL", "")
    internal_key = getattr(settings, "INTERNAL_API_KEY", "")

    if not nexus_ai_url:
        logger.warning("[trigger] NEXUS_AI_URL not set — skipping AI response")
        return

    # 1. Pre-create AI message in DB
    _create_ai_message = sync_to_async(create_ai_message)
    _update_ai_message = sync_to_async(update_ai_message)
    _fail_ai_message = sync_to_async(fail_ai_message)

    try:
        persona = personas[0]
        ai_msg = await _create_ai_message(company, project, topic, persona, triggered_by=triggered_by)
    except Exception as exc:
        logger.warning("[trigger] failed to create AI message: %s", exc)
        return
    
    msg_id = ai_msg["id"]
    channel = topic_channel(topic_id)
    now = datetime.now(dt_timezone.utc).isoformat()

    # 2. Publish message_start
    await publish_async(channel, {
        "type": "message_start",
        "id": msg_id,
        "sender_id": ai_msg["sender_id"],
        "sender_name": ai_msg["sender_name"],
        "sender_avatar": ai_msg["sender_avatar"],  # #148 -- already in _serialise()'s dict
        "sequence": ai_msg["sequence"],
        "created_at": now,
        "triggered_by_id": ai_msg.get("triggered_by_id"),  # whose reply this is (W22)
        "triggered_by_name": ai_msg.get("triggered_by_name"),
        "runbook_run": ai_msg.get("runbook_run"),  # which runbook step this is (W6)
    })

    # 3. Build the minimal TriggerJob payload -- nexus-ai resolves persona/
    #    model config and history itself via its own internal calls back
    #    into nucleus (see nucleus_client.py). context_sources is the one
    #    exception, still built and pushed here for now -- there's an
    #    existing but UNVERIFIED nexus-ai-side endpoint for topic contexts
    #    that queries a different model (TopicContext) than this function
    #    actually uses (ContextSource); switching to it without confirming
    #    they're equivalent risks silently breaking RAG/attached-file search.
    #    Left as a separate, explicitly flagged follow-up -- see #131.

    # _build_context_sources does sync ORM queries — must be wrapped for async context
    context_sources = await sync_to_async(_build_context_sources)(topic, company)

    job_payload = {
        "job_id": str(uuid.uuid4()),
        "msg_id": msg_id,
        "personas": [[str(persona.id), persona.name, persona.description] for persona in personas],
        "topic_id": topic_id,
        "user_message_id": user_message_id,
        "message": user_message,
        "context_sources": context_sources,
        "output_type": output_type,  # M7: "auto" | "chart" | "code" | "terminal" | ...
    }

    # 4. Stream from nexus-ai, relay tokens to Centrifugo
    active_msg_id = msg_id
    streamed_contents: dict[str, list[str]] = {msg_id: []}
    trails: dict[str, list] = {msg_id: []}  # one activity trail per (sub-)message
    ai_error: str | None = None
    stopped = False

    async def should_stop() -> bool:
        signals = stop_signals()
        if await signals.is_stop_requested(active_msg_id):
            return True
        return active_msg_id != msg_id and await signals.is_stop_requested(msg_id)

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            request = client.build_request(
                "POST",
                f"{nexus_ai_url}/api/v1/trigger/swarm/",
                json=job_payload,
                headers={
                    "X-Internal-Key": internal_key,
                    "Content-Type": "application/json",
                },
            )
            # The worker does its own setup before the first byte comes back;
            # a Stop must land during that wait too, not only once lines flow.
            response = await stoppable(client.send(request, stream=True), should_stop)
            try:
                if response.status_code != 200:
                    body = await response.aread()
                    raise RuntimeError(
                        f"nexus-ai /trigger/ returned {response.status_code}: {body.decode()[:300]}"
                    )

                # As in the single relay. A Stop can land on the root bubble
                # or on the delegate currently streaming; either ends the run.
                async for line in stoppable_lines(response.aiter_lines(), should_stop):
                    if not line.startswith("data: "):
                        continue
                    raw = line[6:].strip()
                    if not raw:
                        continue
                    try:
                        event = json.loads(raw)
                        event_type = event.get("type")
                        current_id = event.get("id") or msg_id

                        if event_type == "message_start":
                            # If we see a new ID, we are starting a sub-message for a delegate
                            if current_id != msg_id and current_id not in streamed_contents:
                                persona_id = event.get("persona_id") or str(personas[0].id)
                                from nucleus.models import Persona
                                p_obj = await sync_to_async(lambda: Persona.objects.filter(id=persona_id).first())()
                                if not p_obj:
                                    p_obj = personas[0]
                                new_ai_msg = await _create_ai_message(company, project, topic, p_obj, triggered_by=triggered_by)
                                current_id = new_ai_msg["id"]
                                event.update({
                                    "id": current_id,
                                    "sender_id": new_ai_msg["sender_id"],
                                    "sender_name": new_ai_msg["sender_name"],
                                    "sender_avatar": new_ai_msg["sender_avatar"],
                                    "sequence": new_ai_msg["sequence"],
                                })
                                # Track this new msg metadata for embedding later
                                streamed_contents[f"{current_id}_meta"] = new_ai_msg
                                
                            active_msg_id = current_id
                            streamed_contents[current_id] = []
                            trails[current_id] = []
                            await publish_async(channel, event)

                        elif event_type == "message_delta":
                            delta = event.get("delta") or ""
                            if delta:
                                streamed_contents[active_msg_id].append(delta)
                                await publish_async(channel, {
                                    "type": "message_delta",
                                    "id": active_msg_id,
                                    "delta": delta,
                                })

                        elif event_type == "message_done":
                            # Process completion for the current sub-message
                            final_clean = event.get("content")
                            save_content = final_clean if final_clean is not None else "".join(streamed_contents.get(active_msg_id, []))
                            final_output_type = event.get("output_type") or "text"
                            final_render_as = event.get("render_as") or "text"
                            embed_description = event.get("embed_description")
                            hop_usage = usage_from(event)

                            await _update_ai_message(
                                active_msg_id,
                                save_content,
                                render_as=final_render_as,
                                output_type=final_output_type,
                                usage=hop_usage,
                                activity_trail=trails.get(active_msg_id),
                                answered_by_model=event.get("answered_by_model") or None,
                                recalled=int(event.get("recalled") or 0) or None,
                            )
                            event["id"] = active_msg_id
                            await publish_async(channel, with_usage(event, hop_usage))
                            
                            # M8: Embed AI response
                            _TEXT_EMBEDDABLE = {"text", "code", "auto"}
                            _DESC_EMBEDDABLE = {"html", "form", "terminal"}
                            embed_content = None
                            if final_output_type in _TEXT_EMBEDDABLE and save_content:
                                embed_content = save_content
                            elif final_output_type in _DESC_EMBEDDABLE and embed_description:
                                embed_content = embed_description

                            if embed_content:
                                meta = streamed_contents.get(f"{active_msg_id}_meta", ai_msg)
                                asyncio.create_task(embed_message_async(
                                    message_id=active_msg_id,
                                    company_id=str(company.id),
                                    sequence=meta["sequence"],
                                    topic_id=topic_id,
                                    channel_id=str(topic.channel_id),
                                    project_id=str(project.id),
                                    sender_id=meta["sender_id"] or "",
                                    sender_name=meta["sender_name"] or "",
                                    sender_type="ai",
                                    content=embed_content,
                                    created_at=now,
                                ))
                            
                            # DO NOT BREAK! We must keep the stream open for subsequent swarm agents

                        elif event_type == "tool_call_start":
                            activity = tool_activity_event(active_msg_id, event)
                            if activity:
                                await publish_async(channel, activity)

                        elif event_type == "tool_call_end":
                            ended = tool_activity_end_event(active_msg_id, event)
                            if ended:
                                await publish_async(channel, ended)
                            remember_tool_call(trails.setdefault(active_msg_id, []), event)

                        elif event_type == "swarm_transition":
                            event["id"] = active_msg_id
                            await publish_async(channel, event)

                        elif event_type == "message_error":
                            ai_error = event.get("error") or "Unknown error"
                            logger.warning(
                                "[trigger] nexus-ai reported error for msg %s: %s",
                                active_msg_id, ai_error,
                            )
                            await _fail_ai_message(active_msg_id, ai_error, None, trails.get(active_msg_id))
                            # The single path publishes this; the swarm path used
                            # to fail silently, leaving the client to guess from
                            # stall detection. Same friendly copy, same shape --
                            # the raw exception stays server-side.
                            await publish_async(channel, {
                                "type": "message_error",
                                "id": active_msg_id,
                                "content": "Something went wrong generating this response.",
                            })
                            break

                    except (json.JSONDecodeError, KeyError):
                        continue
            finally:
                await response.aclose()

    except StopRequested:
        stopped = True
    except Exception as exc:
        logger.warning("[trigger] streaming error for msg %s: %s: %s", active_msg_id, type(exc).__name__, exc)

    if stopped:
        await end_stopped_reply(channel, active_msg_id, "".join(streamed_contents.get(active_msg_id, [])), trails.get(active_msg_id))
        if active_msg_id != msg_id:
            await stop_signals().clear(msg_id)


# ── Read messages ──────────────────────────────────────────────────────────────

def list_messages(topic_id: str, limit: int = 100, before_sequence: int = None) -> list[dict]:
    """
    Return up to `limit` messages in a topic, oldest first.

    Pass `before_sequence` (the `sequence` of the oldest message already
    loaded on screen) to page further back in history -- React calls this
    again with that value on scroll-to-top to load older messages, instead
    of being capped at whatever the first `limit` happened to return.
    `sequence` is used as the paging cursor rather than `created_at`
    because it's a strictly increasing per-topic integer (see save_user_message
    etc. below) -- no risk of two messages tying on the same timestamp.
    """
    from nucleus.models import ChatMessage

    reap_orphaned_replies(topic_id)

    qs = ChatMessage.objects.filter(topic_id=topic_id, is_active=True)
    if before_sequence is not None:
        qs = qs.filter(sequence__lt=before_sequence)

    qs = qs.select_related("sender").order_by("-sequence")[:limit]
    return [_serialise(m) for m in reversed(list(qs))]


ORPHAN_AFTER_SECONDS = 180


def reap_orphaned_replies(topic_id: str, older_than_seconds: int = ORPHAN_AFTER_SECONDS) -> list[str]:
    """
    A persona reply still PENDING minutes after it started has no relay left
    to finish it -- nucleus restarted (or was redeployed) mid-run. Fail it
    with that reason so a reader sees why instead of a bubble that never
    ends. Done lazily, when history is read or a stop is asked for; returns
    the ids it failed so the caller can publish message_error for each.
    """
    from nucleus.models import ChatMessage

    cutoff = timezone.now() - timedelta(seconds=older_than_seconds)
    orphans = list(
        ChatMessage.objects.filter(topic_id=topic_id, status=ChatMessage.Status.PENDING, created_at__lt=cutoff, metadata__has_key="persona_id")
        .values_list("id", flat=True)
    )
    for msg_id in orphans:
        fail_ai_message(str(msg_id), "orphaned: no relay finished this reply", ORPHANED_RUN_REASON)
    return [str(i) for i in orphans]


# ── Write messages ─────────────────────────────────────────────────────────────

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


# ── Context sources for TriggerJob ────────────────────────────────────────────

def _build_context_sources(topic, company, persona=None) -> list[dict]:
    """
    Build the context_sources list for TriggerJob.

    Always includes a ChatContext ref (semantic search over past messages).
    Plus any file/web sources attached to the topic that are ready, and the
    project's Recall (W5) unless the persona has recall off.
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

    # 3. Recall -- what the team's personas recorded about the project (W5).
    if persona is None or persona.recall_enabled:
        sources.append({
            "source_id": str(topic.project_id),
            "type": "recall",
            "label": "Recall",
            "collection_id": f"company_{company.id}_recall",
        })

    return sources


# ── Serialiser ────────────────────────────────────────────────────────────────

def _serialise(msg) -> dict:
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
        "render_as": metadata.get("render_as", "text"),    # M7: renderer hint for frontend
        "output_type": metadata.get("output_type", "text"), # M7: semantic type name
        "stopped": bool(metadata.get("stopped")),           # ended by the reader; partial
        "status": msg.status,                                # pending | completed | failed
        # Team AI operations -- reserved with defaults, filled as each lands.
        "activity_trail": metadata.get("activity_trail") or [],
        "preflight": metadata.get("preflight"),
        "approvals": metadata.get("approvals") or [],
        "answered_by_model": metadata.get("answered_by_model"),
        "recalled": int(metadata.get("recalled") or 0),
        "nudges": metadata.get("nudges") or [],
        "usage": metadata.get("usage"),
        "sender_name": sender_name,
        "sender_id": str(msg.sender_id) if msg.sender_id else None,
        "sender_avatar": msg.sender.get_avatar_url() if msg.sender else None,  # #148
        "sender_type": getattr(msg.sender, "user_type", "human") if msg.sender else "system",
        # Frozen at send-time (see create_ai_message) -- None for human/system
        # messages. Lets two personas that have shared the same display name
        # over time (e.g. a deleted-and-recreated "Nova") be told apart, even
        # though sender_name alone can't distinguish them.
        "persona_id": metadata.get("persona_id"),
        # Whose reply this is -- the person who called the persona (W22); None
        # for human/system messages and for replies from before it was recorded.
        "triggered_by_id": metadata.get("triggered_by_id"),
        "triggered_by_name": metadata.get("triggered_by_name"),
        # Which runbook step this reply is -- {id, title, step, of} -- or None (W6).
        "runbook_run": metadata.get("runbook_run"),
        "sequence": msg.sequence,
        "created_at": msg.created_at.isoformat(),
    }


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
    if msg.status != ChatMessage.Status.PENDING:
        return "finished"
    owner_id = (msg.metadata or {}).get("triggered_by_id")
    if owner_id and owner_id != str(user.id):
        return "not_owner"
    return "nudging"


async def repost_untaken_nudges(company, project, topic, msg_id: str, channel: str) -> int:
    """
    Never lost: a nudge the persona did not reach (no tool step came, the
    reply ended or was stopped) becomes an ordinary message from the person
    who sent it. Returns how many were posted.
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
    Ask the relay to end a persona reply that is still streaming in this topic.
    Returns "stopping", "not_found" (not in this topic / not a persona reply),
    "finished" (nothing to stop), "orphaned", or "not_owner" -- a reply is its
    caller's to stop (W22); one from before the caller was recorded keeps the
    old rule (anyone who can read the topic). Sync; the caller wraps it.
    """
    from nucleus.models import ChatMessage

    msg = ChatMessage.objects.filter(id=message_id, topic=topic).first()
    if not msg or not (msg.metadata or {}).get("persona_id"):
        return "not_found"
    if msg.status != ChatMessage.Status.PENDING:
        return "finished"
    owner_id = (msg.metadata or {}).get("triggered_by_id")
    if user is not None and owner_id and owner_id != str(user.id):
        return "not_owner"
    if msg.created_at < timezone.now() - timedelta(seconds=ORPHAN_AFTER_SECONDS):
        fail_ai_message(str(msg.id), "orphaned: no relay finished this reply", ORPHANED_RUN_REASON)
        return "orphaned"
    return "stopping"
