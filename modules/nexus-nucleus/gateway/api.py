"""
Step 6 (docs/NUCLEUS-REVAMP.md) — the MCP gateway and its personal tokens.

The gateway (POST /api/v1/mcp/) makes this server usable AS A TOOL: from
outside (Claude Desktop, Cursor — Authorization: Bearer nxg_…) and from
inside (personas — X-Internal-Key + X-NeuralOps-User). It speaks MCP's
streamable-HTTP wire shape, stateless: one JSON-RPC message per POST
(initialize, tools/list, tools/call, ping; notifications answer 202). GET
answers 405 — there is no server-push stream, and MCP clients handle that.

Every call resolves to a REAL person first and runs with exactly their
rights (owner's rulings 2+3) — there is no master user anywhere on this
road. GATEWAY_ENABLED=false closes the whole door.

Tokens (under /api/v1/gateway/tokens/): minted in the UI by the four roles
holding `gateway.token` (company owner/admin anywhere; project owner/admin
through their project), stored hashed, shown once, revocable; company-level
holders see and revoke every token.
"""
from __future__ import annotations

import hashlib
import json
import logging
import secrets as py_secrets
from typing import Optional

from django.conf import settings
from django.http import HttpResponse
from django.utils import timezone
from ninja import Router, Schema
from ninja.errors import HttpError
from ninja.security import APIKeyHeader, HttpBearer

from authn.auth import SupabaseBearer
from authn.permissions.checker import PermissionChecker
from gateway import tools as gw

logger = logging.getLogger(__name__)

TOKEN_PREFIX = "nxg_"
LAST_USED_EVERY_SECONDS = 60
PROTOCOL_FALLBACK = "2025-03-26"


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# ── who is calling ──────────────────────────────────────────────────────────

class GatewayBearer(HttpBearer):
    """A personal gateway token: Authorization: Bearer nxg_… → its person."""

    def authenticate(self, request, token: str):
        from nucleus.models import GatewayToken

        row = (GatewayToken.objects.select_related("user")
               .filter(token_hash=_hash(token), is_active=True).first())
        if not row or not row.user.is_active:
            return None
        now = timezone.now()
        # last_used is a courtesy stamp, not an audit log — written at most
        # once a minute so a chatty client doesn't turn auth into writes.
        if not row.last_used_at or (now - row.last_used_at).total_seconds() > LAST_USED_EVERY_SECONDS:
            GatewayToken.objects.filter(id=row.id).update(last_used_at=now)
        request.user = row.user
        return row.user


class InternalActor(APIKeyHeader):
    """The inside door (ruling 3): the engine's X-Internal-Key PLUS the real
    triggering person's id in X-NeuralOps-User — rights still apply as that
    person; nothing inside runs as a master user."""

    param_name = "X-Internal-Key"

    def authenticate(self, request, key: str):
        expected = getattr(settings, "INTERNAL_API_KEY", "")
        if not expected or key != expected:
            return None
        user_id = request.headers.get("X-NeuralOps-User", "")
        if not user_id:
            return None
        from django.contrib.auth import get_user_model
        try:
            user = get_user_model().objects.filter(id=user_id, is_active=True).first()
        except Exception:  # noqa: BLE001 — a malformed id is just nobody
            user = None
        if not user:
            return None
        request.user = user
        return user


# ── the MCP endpoint ────────────────────────────────────────────────────────

mcp_router = Router(tags=["Gateway"], auth=[GatewayBearer(), InternalActor()])


def _schema(props: dict, required: list[str]) -> dict:
    return {"type": "object", "properties": props, "required": required}


TOOL_DEFS = [
    {"name": "list_projects",
     "description": "The projects you can see on this NeuralOps server.",
     "inputSchema": _schema({}, [])},
    {"name": "list_topics",
     "description": "The channels and topics of one project you can see.",
     "inputSchema": _schema({"project_id": {"type": "string"}}, ["project_id"])},
    {"name": "post_message",
     "description": "Post a plain message into a topic (no AI reply — use ask_persona for that).",
     "inputSchema": _schema({"topic_id": {"type": "string"},
                             "content": {"type": "string"}}, ["topic_id", "content"])},
    {"name": "ask_persona",
     "description": "Ask one of the project's AI personas a question in a topic and wait for its reply.",
     "inputSchema": _schema({"topic_id": {"type": "string"},
                             "persona": {"type": "string"},
                             "message": {"type": "string"}}, ["topic_id", "persona", "message"])},
    {"name": "search_memory",
     "description": "Search across the chats you can see — by meaning first, literally as a fallback.",
     "inputSchema": _schema({"query": {"type": "string"},
                             "project_id": {"type": "string"}}, ["query"])},
]

_DISPATCH = {
    "list_projects": lambda user: gw.list_projects(user),
    "list_topics": lambda user, project_id: gw.list_topics(user, project_id),
    "post_message": lambda user, topic_id, content: gw.post_message(user, topic_id, content),
    "ask_persona": lambda user, topic_id, persona, message: gw.ask_persona(user, topic_id, persona, message),
    "search_memory": lambda user, query, project_id=None: gw.search_memory(user, query, project_id),
}


def _rpc_error(rpc_id, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": rpc_id, "error": {"code": code, "message": message}}


def _tool_error(text: str) -> dict:
    return {"content": [{"type": "text", "text": text}], "isError": True}


async def _call_tool(user, params: dict) -> dict:
    name = str(params.get("name") or "")
    arguments = params.get("arguments") or {}
    fn = _DISPATCH.get(name)
    if fn is None:
        return _tool_error(f"unknown tool {name!r}")
    if not isinstance(arguments, dict):
        return _tool_error("arguments must be an object")
    try:
        out = await fn(user, **arguments)
    except gw.GatewayToolError as exc:
        return _tool_error(str(exc))
    except TypeError as exc:
        return _tool_error(f"bad arguments for {name}: {exc}")
    return {"content": [{"type": "text",
                         "text": json.dumps(out, ensure_ascii=False, default=str)}],
            "isError": False}


@mcp_router.post("/")
async def mcp_endpoint(request):
    """One JSON-RPC message in, one answer out (stateless streamable HTTP)."""
    if not getattr(settings, "GATEWAY_ENABLED", True):
        raise HttpError(403, "The MCP gateway is turned off on this server (GATEWAY_ENABLED).")
    try:
        body = json.loads(request.body or b"")
    except ValueError:
        return _rpc_error(None, -32700, "parse error: the body isn't JSON")
    if not isinstance(body, dict):
        return _rpc_error(None, -32600, "batch requests aren't supported")

    method = str(body.get("method") or "")
    rpc_id = body.get("id")
    params = body.get("params") or {}

    if rpc_id is None:
        # A notification (e.g. notifications/initialized): acknowledged, no body.
        return HttpResponse(status=202)

    if method == "initialize":
        result = {
            "protocolVersion": str(params.get("protocolVersion") or PROTOCOL_FALLBACK),
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "NeuralOps",
                           "version": getattr(settings, "NEURALOPS_VERSION", "unknown")},
        }
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": TOOL_DEFS}
    elif method == "tools/call":
        result = await _call_tool(request.auth, params)
    else:
        return _rpc_error(rpc_id, -32601, f"unknown method {method!r}")

    return {"jsonrpc": "2.0", "id": rpc_id, "result": result}


# ── personal tokens ─────────────────────────────────────────────────────────

tokens_router = Router(tags=["Gateway"], auth=SupabaseBearer())


class TokenCreateIn(Schema):
    name: str
    # Company-level holders may mint for someone else; the token still only
    # ever acts AS that person.
    user_id: Optional[str] = None


class TokenOut(Schema):
    id: str
    name: str
    user_id: str
    user_email: str
    created_at: str
    last_used_at: Optional[str] = None


class TokenCreatedOut(TokenOut):
    token: str  # shown exactly once


def _resolve_company():
    from workspace.services import get_company

    company = get_company()
    if not company:
        raise HttpError(503, "Server not initialised.")
    return company


def _mint_level(user, company) -> str | None:
    """'company' (owner/admin anywhere), 'project' (owner/admin of at least
    one project), or None — the four-roles rule (Step 6 ruling 2)."""
    if PermissionChecker.can(user, "gateway.token", company=company):
        return "company"
    from authn.permissions.row_rules import visible_projects
    for project in visible_projects(user, company):
        if PermissionChecker.can(user, "gateway.token", obj=project):
            return "project"
    return None


def _out(row) -> dict:
    return {
        "id": str(row.id), "name": row.name,
        "user_id": str(row.user_id), "user_email": row.user.email,
        "created_at": row.created_at.isoformat(),
        "last_used_at": row.last_used_at.isoformat() if row.last_used_at else None,
    }


@tokens_router.post("/", response=TokenCreatedOut)
def create_token(request, payload: TokenCreateIn):
    """Mint a token. The raw value appears HERE and never again."""
    from django.contrib.auth import get_user_model
    from nucleus.models import GatewayToken

    user = request.auth
    company = _resolve_company()
    level = _mint_level(user, company)
    if level is None:
        raise HttpError(403, "Only a company or project owner/admin can create gateway tokens.")

    target = user
    if payload.user_id and payload.user_id != str(user.id):
        if level != "company":
            raise HttpError(403, "Only a company owner/admin can create a token for someone else.")
        try:
            target = get_user_model().objects.filter(
                id=payload.user_id, is_active=True, user_type="human").first()
        except Exception:  # noqa: BLE001
            target = None
        if not target:
            raise HttpError(404, "No such user on this server.")

    name = (payload.name or "").strip()[:100] or "token"
    raw = TOKEN_PREFIX + py_secrets.token_urlsafe(32)
    row = GatewayToken.objects.create(
        user=target, created_by=user, name=name, token_hash=_hash(raw))
    logger.info("[gateway] token %r created by %s for %s", name, user.email, target.email)
    return {**_out(row), "token": raw}


@tokens_router.get("/", response=list[TokenOut])
def list_tokens(request):
    """Your tokens (and ones you minted); company-level holders see all."""
    from django.db.models import Q
    from nucleus.models import GatewayToken

    user = request.auth
    company = _resolve_company()
    qs = GatewayToken.objects.filter(is_active=True).select_related("user")
    if not PermissionChecker.can(user, "gateway.token", company=company):
        qs = qs.filter(Q(user=user) | Q(created_by=user))
    return [_out(r) for r in qs]


@tokens_router.delete("/{token_id}/", response=dict)
def revoke_token(request, token_id: str):
    """Revoke: yours, one you minted, or any (company-level holders)."""
    from nucleus.models import GatewayToken

    user = request.auth
    company = _resolve_company()
    try:
        row = GatewayToken.objects.filter(id=token_id, is_active=True).first()
    except Exception:  # noqa: BLE001
        row = None
    if not row:
        raise HttpError(404, "No such token.")
    allowed = (
        row.user_id == user.id
        or row.created_by_id == user.id
        or PermissionChecker.can(user, "gateway.token", company=company)
    )
    if not allowed:
        raise HttpError(403, "You can only revoke your own tokens.")
    row.is_active = False
    row.save(update_fields=["is_active"])
    logger.info("[gateway] token %s revoked by %s", row.id, user.email)
    return {"ok": True}
