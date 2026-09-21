"""
Short-lived signed tickets, shared by every worker feature a browser connects
to directly (the terminal's WebSocket, the live browser's).

A WebSocket in the browser cannot carry an Authorization header, so nucleus --
which did authenticate the person -- signs a ticket with the shared internal
secret and hands it over; the worker verifies the signature, the expiry and
the claims it needs. Nucleus keeps its own copy of sign_ticket (it must not
import the worker), so any change here changes there too.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any

TICKET_TTL_SECONDS = 60


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _signature(payload: str, secret: str) -> str:
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


def sign_ticket(claims: dict[str, Any], secret: str, ttl: int = TICKET_TTL_SECONDS, now: float | None = None) -> str:
    """`<base64url claims>.<hmac>` -- what nucleus issues (its copy lives in workspace/services.py)."""
    body = dict(claims)
    body["exp"] = int((now if now is not None else time.time()) + ttl)
    payload = _b64(json.dumps(body, separators=(",", ":"), sort_keys=True).encode())
    return f"{payload}.{_signature(payload, secret)}"


def verify_ticket(
    ticket: str | None,
    secret: str,
    *,
    require: tuple[str, ...] = ("project_id",),
    now: float | None = None,
) -> dict[str, Any] | None:
    """The claims when the signature holds, the ticket is live and `require` is present; None otherwise."""
    if not ticket or "." not in ticket:
        return None
    payload, signature = ticket.rsplit(".", 1)
    if not hmac.compare_digest(signature, _signature(payload, secret)):
        return None
    try:
        claims = json.loads(_unb64(payload))
    except (ValueError, TypeError):
        return None
    if not isinstance(claims, dict) or not isinstance(claims.get("exp"), int):
        return None
    if claims["exp"] < (now if now is not None else time.time()):
        return None
    if any(not claims.get(key) for key in require):
        return None
    return claims
