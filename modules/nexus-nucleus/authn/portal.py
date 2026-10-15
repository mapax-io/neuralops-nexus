"""
Step 4 (docs/NUCLEUS-REVAMP.md) — talking to the sign-in portal's device-code
functions.

The flow, in plain words: a fresh install asks the portal for a short code;
the person signs in at the portal (settings.NEURALOPS_PORTAL_URL) and types
the code there; this server polls until the portal hands back a Supabase
access token proving who typed it. Same idea as signing in on a TV.

Only this file knows the two edge-function URLs
(settings.SUPABASE_DEVICE_REQUEST_URL / SUPABASE_DEVICE_POLL_URL). Their
exact response keys can't be read from this repo, so parsing is TOLERANT:
both the documented names and the usual OAuth device-flow names are
accepted. If the functions are dead or renamed, only this file (or the two
URL env vars) changes — nothing else in nucleus knows the portal exists.
The contract this file expects is written down in docs/NUCLEUS-REVAMP.md
Step 4.
"""
from __future__ import annotations

import httpx
from django.conf import settings

TIMEOUT_SECONDS = 15
DEFAULT_EXPIRES_IN = 900  # 15 minutes, used when the portal doesn't say


class PortalError(Exception):
    """The portal could not be reached, or answered in a shape we don't know."""


def _headers() -> dict:
    # Supabase edge functions usually require the project's anon key. Sent
    # under both names Supabase accepts; harmless if the function ignores it.
    headers = {"Content-Type": "application/json"}
    anon = getattr(settings, "SUPABASE_ANON_KEY", "")
    if anon:
        headers["apikey"] = anon
        headers["Authorization"] = f"Bearer {anon}"
    return headers


def _post(url: str, payload: dict) -> dict:
    try:
        response = httpx.post(url, json=payload, headers=_headers(), timeout=TIMEOUT_SECONDS)
    except httpx.HTTPError as exc:
        raise PortalError(f"Could not reach the sign-in portal: {exc}") from exc
    if response.status_code >= 500:
        raise PortalError(f"The sign-in portal failed ({response.status_code}).")
    try:
        data = response.json()
    except ValueError:
        raise PortalError("The sign-in portal answered with something that isn't JSON.")
    if not isinstance(data, dict):
        raise PortalError("The sign-in portal answered in a shape we don't know.")
    return data


def request_device_code() -> dict:
    """
    Ask the portal for a fresh code. Returns
    {"code", "request_id", "expires_in"}, or raises PortalError.
    """
    data = _post(
        settings.SUPABASE_DEVICE_REQUEST_URL,
        {"server_url": getattr(settings, "NEURALOPS_SERVER_URL", "")},
    )
    code = data.get("code") or data.get("user_code")
    request_id = data.get("request_id") or data.get("device_code") or data.get("id")
    if not code or not request_id:
        raise PortalError(
            "The sign-in portal didn't return a code. "
            "(Expected keys: code/user_code and request_id/device_code.)"
        )
    try:
        expires_in = int(data.get("expires_in") or DEFAULT_EXPIRES_IN)
    except (TypeError, ValueError):
        expires_in = DEFAULT_EXPIRES_IN
    return {"code": str(code), "request_id": str(request_id), "expires_in": expires_in}


def poll_device_code(request_id: str) -> dict:
    """
    One poll. Returns {"status": "pending"} while nobody has typed the code,
    or {"status": "claimed", "access_token": ...} once someone signed in at
    the portal and typed it. Raises PortalError when the portal can't be
    reached, the request expired/was declined, or the answer makes no sense.
    """
    data = _post(
        settings.SUPABASE_DEVICE_POLL_URL,
        # Both spellings of the id, so either implementation finds its own.
        {"request_id": request_id, "device_code": request_id},
    )
    token = data.get("access_token") or data.get("token")
    if token:
        return {"status": "claimed", "access_token": str(token)}
    status = str(data.get("status") or "").lower()
    if status in ("", "pending", "authorization_pending", "waiting"):
        return {"status": "pending"}
    if status in ("expired", "denied", "declined"):
        raise PortalError(f"The sign-in request is {status}. Start again from the setup screen.")
    raise PortalError(f"The sign-in portal answered with an unknown status: {status!r}.")
