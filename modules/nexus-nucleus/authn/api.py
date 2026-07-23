import hashlib
import re

from django.conf import settings
from django.utils import timezone
from ninja import Router, Schema
from ninja.errors import HttpError

from .schema import AuthInitResponse, AuthStatusResponse, AuthVerifyResponse, SignInRequest, SignInResponse
from .services import DeviceAuthError, SignInError, auth_init, auth_status, auth_verify, signin_with_supabase_token
from .supabase import SupabaseTokenError
from . import workspace_services as ws_svc
from . import team_services as team_svc
from authn.auth import SupabaseBearer


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


# ── Change display name ───────────────────────────────────────────────────────

class ChangeUsernameIn(Schema):
    new_name: str
    topic_id: str


class ChangeUsernameOut(Schema):
    ok: bool
    display_name: str


_USERNAME_RE = re.compile(r'^[a-zA-Z0-9_]{2,30}$')


@router.post("/change-username/", response=ChangeUsernameOut, auth=SupabaseBearer())
def change_username(request, payload: ChangeUsernameIn):
    from django.contrib.auth import get_user_model
    from chat.services import save_system_message, publish, topic_channel
    from nucleus.models import ChatTopic, Company

    User = get_user_model()
    user = request.auth

    name = payload.new_name.strip()

    if not _USERNAME_RE.match(name):
        raise HttpError(400, "Username must be 2-30 characters, letters/numbers/underscore only.")

    if User.objects.filter(display_name=name).exclude(pk=user.pk).exists():
        raise HttpError(409, f"'{name}' is already taken on this server.")

    old_name = user.get_display_name()
    user.display_name = name
    user.save(update_fields=["display_name"])

    try:
        topic = ChatTopic.objects.get(id=payload.topic_id, is_active=True)
        company = Company.objects.filter(is_active=True).first()
        sys_msg = save_system_message(
            company=company,
            project=topic.project,
            topic=topic,
            content=f"{old_name} changed their username to {name}",
        )
        publish(topic_channel(payload.topic_id), sys_msg)
    except Exception:
        pass

    return {"ok": True, "display_name": name}
