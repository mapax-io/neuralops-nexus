import hashlib

from django.conf import settings
from django.utils import timezone
from ninja import Router, Schema
from ninja.errors import HttpError

from .schema import AuthInitResponse, AuthStatusResponse, AuthVerifyResponse, SignInRequest, SignInResponse
from .services import DeviceAuthError, SignInError, auth_init, auth_status, auth_verify, signin_with_supabase_token
from .supabase import SupabaseTokenError
from . import workspace_services as ws_svc
from . import team_services as team_svc


router = Router(tags=["Authentication"])


# ── Server config (public) ───────────────────────────────────────────────────

class ServerConfigOut(Schema):
    server_url: str


@router.get("/config/", response=ServerConfigOut, auth=None)
def server_config(request):
    """
    Returns the public server URL (NEURALOPS_SERVER_URL env var).
    Used by the frontend so users know what address to share.
    No authentication required.
    """
    return {"server_url": getattr(settings, "NEURALOPS_SERVER_URL", "")}


# ── Supabase JWT sign-in ─────────────────────────────────────────────────────

@router.post("/signin", response=SignInResponse)
def signin(request, payload: SignInRequest):
    try:
        return signin_with_supabase_token(payload.access_token)
    except (SignInError, SupabaseTokenError) as exc:
        raise HttpError(401, str(exc))


# ── Device activation flow ───────────────────────────────────────────────────

@router.get("/init/", response=AuthInitResponse)
def init(request):
    try:
        return auth_init()
    except DeviceAuthError as exc:
        raise HttpError(502, f"Could not reach activation service: {exc}")


@router.get("/status/", response=AuthStatusResponse)
def status(request):
    return auth_status()


# ── Server connection verify ─────────────────────────────────────────────────

@router.get("/verify/", response=AuthVerifyResponse)
def verify(request):
    """
    Called by the React app when the user connects to a server.
    Verifies the Supabase JWT and checks if the user is allowed on this server.
    If the user has a pending invitation, it is auto-accepted here.
    Returns 200 if allowed, 401 if token invalid, 403 if not allowed.
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HttpError(401, "Missing authorization token")

    token = auth_header.split(" ", 1)[1]
    try:
        return auth_verify(token)
    except SupabaseTokenError as exc:
        raise HttpError(401, str(exc))
    except PermissionError as exc:
        raise HttpError(403, str(exc))
