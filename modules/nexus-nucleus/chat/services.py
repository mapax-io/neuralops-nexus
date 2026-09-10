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

def create_ai_message(company, project, topic, persona, render_as: str = "text") -> dict:
    """Pre-create a PENDING ChatMessage for the AI response."""
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
        },
    )
    return _serialise(msg)


def update_ai_message(
    message_id: str,
    content: str,
    render_as: str = "text",
    output_type: str = "text",
) -> None:
    """Update the AI message content and mark COMPLETED."""
    from nucleus.models import ChatMessage

    msg = ChatMessage.objects.filter(id=message_id).first()
    if not msg:
        return

    # Merge render_as into existing metadata
    metadata = dict(msg.metadata or {})
    metadata["render_as"] = render_as
    metadata["output_type"] = output_type

    ChatMessage.objects.filter(id=message_id).update(
        content=content,
        status=ChatMessage.Status.COMPLETED,
        metadata=metadata,
    )


def fail_ai_message(message_id: str, error: str, display_content: str | None = None) -> None:
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
    ChatMessage.objects.filter(id=message_id).update(
        content=display_content or "Something went wrong generating this response.",
        status=ChatMessage.Status.FAILED,
        metadata=metadata,
    )

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
        ai_msg = await _create_ai_message(company, project, topic, persona)
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
        "persona_id": str(persona.id),
        "topic_id": topic_id,
        "user_message_id": user_message_id,
        "message": user_message,
        "context_sources": context_sources,
        "output_type": output_type,  # M7: "auto" | "chart" | "code" | "terminal" | ...
    }

    # 4. Stream from nexus-ai, relay tokens to Centrifugo
    streamed_content: list[str] = []
    final_output_type = "text"
    final_render_as = "text"
    final_clean_content: str | None = None
    embed_description: str | None = None
    ai_error: str | None = None
    ai_error_code: str | None = None

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream(
                "POST",
                f"{nexus_ai_url}/api/v1/trigger/",
                json=job_payload,
                headers={
                    "X-Internal-Key": internal_key,
                    "Content-Type": "application/json",
                },
            ) as response:
                if response.status_code != 200:
                    body = await response.aread()
                    raise RuntimeError(
                        f"nexus-ai /trigger/ returned {response.status_code}: {body.decode()[:300]}"
                    )

                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    raw = line[6:].strip()
                    if not raw:
                        continue
                    try:
                        event = json.loads(raw)
                        event_type = event.get("type")

                        if event_type == "message_delta":
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

    except Exception as exc:
        logger.warning("[trigger] streaming error for msg %s: %s", msg_id, exc)

    # Use nexus-ai's clean content if available, else fall back to streamed
    save_content = (
        final_clean_content
        if final_clean_content is not None
        else "".join(streamed_content)
    )

    # 5. Save full content to DB + publish message_done (or FAILED + message_error)
    try:
        if ai_error:
            display = ai_error if ai_error_code == "mcp_reauth_required" else None
            await _fail_ai_message(msg_id, ai_error, display)
        else:
            await _update_ai_message(
                msg_id,
                save_content,
                render_as=final_render_as,
                output_type=final_output_type,
            )
    except Exception as exc:
        logger.warning("[trigger] failed to update AI message %s: %s", msg_id, exc)

    await publish_async(channel, {
        "type": "message_error" if ai_error else "message_done",
        "id": msg_id,
        # Same friendly copy as fail_ai_message()'s DB write -- the raw
        # exception text (ai_error) stays server-side only (logged above +
        # stored in ChatMessage.metadata.error_detail), never shipped to
        # the browser over Centrifugo.
            "content": (ai_error if ai_error_code == "mcp_reauth_required"
                else "Something went wrong generating this response.") if ai_error else save_content,
        "output_type": final_output_type,   # M7: e.g. "chart"
        "render_as": final_render_as,        # M7: e.g. "html"
    })

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
        ai_msg = await _create_ai_message(company, project, topic, persona)
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
    ai_error: str | None = None

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream(
                "POST",
                f"{nexus_ai_url}/api/v1/trigger/swarm/",
                json=job_payload,
                headers={
                    "X-Internal-Key": internal_key,
                    "Content-Type": "application/json",
                },
            ) as response:
                if response.status_code != 200:
                    body = await response.aread()
                    raise RuntimeError(
                        f"nexus-ai /trigger/ returned {response.status_code}: {body.decode()[:300]}"
                    )

                async for line in response.aiter_lines():
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
                                new_ai_msg = await _create_ai_message(company, project, topic, p_obj)
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
                            
                            await _update_ai_message(
                                active_msg_id,
                                save_content,
                                render_as=final_render_as,
                                output_type=final_output_type,
                            )
                            event["id"] = active_msg_id
                            await publish_async(channel, event)
                            
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

                        elif event_type == "swarm_transition":
                            event["id"] = active_msg_id
                            await publish_async(channel, event)

                        elif event_type == "message_error":
                            ai_error = event.get("error") or "Unknown error"
                            logger.warning(
                                "[trigger] nexus-ai reported error for msg %s: %s",
                                active_msg_id, ai_error,
                            )
                            await _fail_ai_message(active_msg_id, ai_error)
                            break

                    except (json.JSONDecodeError, KeyError):
                        continue

    except Exception as exc:
        logger.warning("[trigger] streaming error for msg %s: %s", active_msg_id, exc)
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

    qs = ChatMessage.objects.filter(topic_id=topic_id, is_active=True)
    if before_sequence is not None:
        qs = qs.filter(sequence__lt=before_sequence)

    qs = qs.select_related("sender").order_by("-sequence")[:limit]
    return [_serialise(m) for m in reversed(list(qs))]


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

def _build_context_sources(topic, company) -> list[dict]:
    """
    Build the context_sources list for TriggerJob.

    Always includes a ChatContext ref (semantic search over past messages).
    Plus any file/web sources attached to the topic that are ready.
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
        "sender_name": sender_name,
        "sender_id": str(msg.sender_id) if msg.sender_id else None,
        "sender_avatar": msg.sender.get_avatar_url() if msg.sender else None,  # #148
        "sender_type": getattr(msg.sender, "user_type", "human") if msg.sender else "system",
        # Frozen at send-time (see create_ai_message) -- None for human/system
        # messages. Lets two personas that have shared the same display name
        # over time (e.g. a deleted-and-recreated "Nova") be told apart, even
        # though sender_name alone can't distinguish them.
        "persona_id": metadata.get("persona_id"),
        "sequence": msg.sequence,
        "created_at": msg.created_at.isoformat(),
    }
