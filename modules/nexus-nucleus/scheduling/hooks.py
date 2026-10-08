"""
scheduling/hooks.py -- Inbound hooks (W12): a URL another system POSTs to so a
persona answers in a topic, with nobody signed in.

The one public write path in nucleus, so the rules are tight: the token is
never stored (only its sha256 and its last four characters), an unknown token
is a flat 404 that says nothing about whether it ever existed, every fire is
counted against a per-hook, per-minute budget, and the fire acts as the person
who created the hook -- whose right to call personas in the topic is re-checked
every time, exactly as a schedule's creator's is.

Posting and triggering go through the same two functions a typed @mention uses
(chat/services.py:save_user_message and chat/api.py:_trigger_personas); nothing
about an AI reply is re-implemented here.
"""
import hashlib
import json
import logging
import secrets

from asgiref.sync import sync_to_async
from django.db.models import F
from django.utils import timezone

from chat import api as chat_api
from chat import services as chat_svc
from chat.stop_signals import signal_store

logger = logging.getLogger(__name__)

TEXT_MAX = 4_000
DATA_MAX_BYTES = 32 * 1024
LABEL_MAX = 80
# Per hook, per minute. A sender that loops gets 429 and a Retry-After, not a
# topic full of messages.
FIRES_PER_MINUTE = 30
RATE_WINDOW_SECONDS = 60
_RATE_KEY = "nx:hook:{hook_id}:{window}"
# 32 bytes of urlsafe randomness -- 43 characters, the same shape a webhook URL
# carries everywhere else.
TOKEN_BYTES = 32
HINT_CHARS = 4


class HookError(Exception):
    """A fire that will not happen; `status` is the HTTP answer, `detail` what the sender is told."""

    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_token() -> tuple[str, str, str]:
    """(token, its hash, its hint). The token is returned once and never stored."""
    token = secrets.token_urlsafe(TOKEN_BYTES)
    return token, token_hash(token), token[-HINT_CHARS:]


# ── Management (under the topic, like schedules) ──────────────────────────────

def list_hooks(topic):
    from nucleus.models import InboundHook
    return list(
        InboundHook.objects.filter(topic=topic, is_active=True)
        .select_related("persona", "created_by")
        .order_by("-created_at")
    )


def get_hook(topic, hook_id: str):
    from nucleus.models import InboundHook
    return InboundHook.objects.filter(topic=topic, id=hook_id, is_active=True).select_related("persona", "created_by").first()


def create_hook(company, project, topic, user, persona, label: str = ""):
    """The hook and the token that reaches it -- the only time the token exists."""
    from nucleus.models import InboundHook

    token, hashed, hint = new_token()
    hook = InboundHook.objects.create(
        company=company, project=project, topic=topic, persona=persona, created_by=user,
        label=(label or "").strip()[:LABEL_MAX], token_hash=hashed, token_hint=hint,
    )
    return hook, token


def regenerate_token(hook) -> str:
    """A new token for an existing hook; the old one stops working at once."""
    token, hashed, hint = new_token()
    hook.token_hash = hashed
    hook.token_hint = hint
    hook.save(update_fields=["token_hash", "token_hint", "updated_at"])
    return token


def patch_hook(hook, *, label=None, is_paused=None):
    fields = []
    if label is not None:
        hook.label = (label or "").strip()[:LABEL_MAX]
        fields.append("label")
    if is_paused is not None:
        hook.is_paused = bool(is_paused)
        fields.append("is_paused")
    if fields:
        hook.save(update_fields=[*fields, "updated_at"])
    return hook


def delete_hook(hook) -> None:
    hook.soft_delete()


def serialise_hook(hook, token: str | None = None) -> dict:
    """The hook as the pane sees it. `token` is set ONLY by create and regenerate."""
    out = {
        "id": str(hook.id),
        "topic_id": str(hook.topic_id),
        "persona_id": str(hook.persona_id),
        "persona_name": hook.persona.name,
        "label": hook.label or "",
        "token_hint": hook.token_hint or "",
        "created_by_id": str(hook.created_by_id) if hook.created_by_id else None,
        "created_by_name": hook.created_by.get_display_name() if hook.created_by else None,
        "is_paused": hook.is_paused,
        "fire_count": hook.fire_count,
        "last_fired_at": hook.last_fired_at.isoformat() if hook.last_fired_at else None,
        "last_status": hook.last_status,
        "last_error": hook.last_error or "",
        "created_at": hook.created_at.isoformat(),
    }
    if token is not None:
        out["token"] = token
    return out


# ── Firing ────────────────────────────────────────────────────────────────────

def hook_for_token(token: str):
    """The live hook a token reaches, or None -- looked up by hash, never by the token."""
    from nucleus.models import InboundHook
    if not token:
        return None
    # Archiving a project, channel or topic is a soft delete on THAT row only --
    # nothing cascades -- so a hook's own is_active is not enough: without these,
    # a token kept firing into an archived chat forever (audit, 2026-09-21).
    return (
        InboundHook.objects.filter(
            token_hash=token_hash(token), is_active=True,
            topic__is_active=True, topic__channel__is_active=True,
            project__is_active=True, company__is_active=True,
        )
        .select_related("persona", "persona__model", "topic", "project", "company", "created_by")
        .first()
    )


def message_for(persona, text: str, data=None) -> str:
    """
    What the topic sees: the mention and the sender's line, with any structured
    data fenced under it. The sender's text is not trusted markdown -- a line of
    backticks in it would otherwise close the fence and let it write its own.
    """
    body = f"@{persona.name} {fence_safe(text.strip())}"
    if data is None:
        return body
    return f"{body}\n\n```json\n{json.dumps(data, indent=2, sort_keys=True, default=str)}\n```"


def fence_safe(text: str) -> str:
    """The text with any line that opens or closes a code fence defused."""
    return "\n".join(
        (" " + line) if line.lstrip().startswith("```") else line
        for line in text.splitlines()
    ) or text


def validate_payload(text: str | None, data) -> tuple[str, object | None]:
    """The text and data a fire may carry; raises HookError with the sender's answer."""
    text = (text or "").strip()
    if not text:
        raise HookError(400, "Send some text for the persona to answer.")
    if len(text) > TEXT_MAX:
        raise HookError(413, f"The text is longer than {TEXT_MAX:,} characters.")
    if data is not None:
        try:
            size = len(json.dumps(data, default=str).encode())
        except (TypeError, ValueError):
            raise HookError(400, "The data must be JSON.")
        if size > DATA_MAX_BYTES:
            raise HookError(413, f"The data is larger than {DATA_MAX_BYTES // 1024} KB.")
    return text, data


async def within_rate_limit(hook) -> bool:
    """
    One fire's worth of budget for this hook this minute. A store outage closes
    the door rather than opening it: this is the one endpoint anyone on the
    internet can reach, so "the limiter is down" must not mean "no limit".
    """
    window = int(timezone.now().timestamp() // RATE_WINDOW_SECONDS)
    key = _RATE_KEY.format(hook_id=hook.id, window=window)
    try:
        count = await signal_store().incr(key, RATE_WINDOW_SECONDS)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[hook] rate limit unavailable for %s: %s", hook.id, type(exc).__name__)
        raise HookError(503, "This hook cannot be accepted right now; try again shortly.") from exc
    return count <= FIRES_PER_MINUTE


def _record(hook, *, ok: bool, error: str = "") -> None:
    from nucleus.models import InboundHook

    fields = {
        "last_fired_at": timezone.now(),
        "last_status": InboundHook.FireStatus.SUCCESS if ok else InboundHook.FireStatus.FAILED,
        "last_error": "" if ok else error[:2000],
    }
    if ok:
        # Counted in the database, not from a value read a moment ago: two fires
        # at once would otherwise record one.
        fields["fire_count"] = F("fire_count") + 1
    InboundHook.objects.filter(id=hook.id).update(**fields)


def _actor_problem(hook) -> str | None:
    """Why this hook's creator may no longer call its persona here, or None."""
    from authn.permissions.checker import PermissionChecker

    if hook.created_by is None:
        return "The person who created this hook no longer has an account here."
    if not PermissionChecker.can(hook.created_by, "persona.mention", obj=hook.topic):
        return "The person who created this hook can no longer call personas in that chat."
    if not hook.persona.is_active:
        return "The persona this hook calls is gone."
    # model is NOT NULL, so "no model" means the model row was removed (a soft
    # delete leaves the pointer). The trigger path would then fail the reply out
    # of the sender's sight, while the hook answered ok and counted a success
    # (audit, 2026-09-21).
    model = hook.persona.model
    if model is None or not model.is_active:
        return "The persona this hook calls has no working model, so it cannot answer."
    return None


async def fire(hook, text: str, data=None) -> dict:
    """
    Post the sender's line as the hook's creator and let the persona answer.
    Raises HookError for anything the sender should be told.
    """
    # The budget is spent FIRST: a paused hook or a bad payload is still work
    # this server did for whoever holds the token, so it must count.
    if not await within_rate_limit(hook):
        raise HookError(429, f"More than {FIRES_PER_MINUTE} fires in a minute; try again shortly.")
    if hook.is_paused:
        raise HookError(409, "This hook is paused.")
    text, data = validate_payload(text, data)

    problem = await sync_to_async(_actor_problem)(hook)
    if problem:
        await sync_to_async(_record)(hook, ok=False, error=problem)
        raise HookError(403, problem)

    msg = await sync_to_async(chat_svc.save_user_message)(
        hook.company, hook.project, hook.topic, hook.created_by, message_for(hook.persona, text, data),
    )
    channel = chat_svc.topic_channel(str(hook.topic_id))
    await chat_svc.publish_async(channel, {**msg, "type": "message"})
    refusals = await chat_api._trigger_personas(
        [hook.persona], hook.company, hook.project, hook.topic, str(hook.topic_id),
        msg, text, "auto", False, None, hook.created_by,
    )
    if refusals:
        # The message posted; the persona will not answer it. Say so rather than
        # report a success the sender cannot verify.
        why = refusals[0].get("message") or "The persona did not answer this fire."
        await sync_to_async(_record)(hook, ok=False, error=why)
        raise HookError(409, why)
    await sync_to_async(_record)(hook, ok=True)
    return msg
