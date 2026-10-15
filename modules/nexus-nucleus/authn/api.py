import hashlib
import re
from typing import Optional

from django.conf import settings
from django.utils import timezone
from ninja import File, Router, Schema
from ninja.files import UploadedFile
from ninja.errors import HttpError

from .schema import (
    AuthVerifyResponse, LocalUserOut, MyPermissionsOut, RolesOut,
    SetRoleRightsIn, SetRoleRightsOut, SignInRequest, SignInResponse,
)
from .services import (
    AvatarError, LocalSignInError, RoleEditError, SetupError, SignInError,
    auth_verify, claim_install, clear_profile_photo, list_roles, local_signin,
    my_permissions, server_needs_owner, set_local_password, set_role_rights,
    set_profile_photo, signin_with_supabase_token,
)
from .portal import PortalError, poll_device_code, request_device_code
from .supabase import SupabaseTokenError, verify_supabase_token
from .versions import read_module_versions
from authn.auth import SupabaseBearer
from authn.permissions.checker import PermissionChecker


router = Router(tags=["Authentication"])

# Mounted at /api/v1/me/ (see core/urls.py) -- "things about the caller",
# separate from /auth/ which is about establishing the connection.
me_router = Router(tags=["Me"], auth=SupabaseBearer())
# Mounted at /api/v1/roles/ -- editing what a role GRANTS, which is different
# from assigning a role to someone (workspace/members).
roles_router = Router(tags=["Roles"], auth=SupabaseBearer())


# ── Server config (public) ───────────────────────────────────────────────────

class ServerConfigOut(Schema):
    server_url: str
    # Self-host version check (#170) -- public/no-auth so the frontend can
    # preview a saved server's version (ServerList.tsx) before the user
    # clicks Connect, without touching /auth/verify/ (which has real side
    # effects: creates the user record, assigns avatar/display name, etc.
    # -- not something to trigger just for a version peek).
    server_version: Optional[str] = None
    # Per-module versions -- informational only, see AuthVerifyResponse's
    # matching fields in schema.py for the full explanation.
    nucleus_version: Optional[str] = None
    nexus_ai_version: Optional[str] = None
    nexus_transport_version: Optional[str] = None

class InvitePreviewOut(Schema):
    company_name: str
    inviter_name: str
    email: str
    expires_at: Optional[str] = None

class ChangeUsernameIn(Schema):
    new_name: str
    topic_id: str

class ChangeUsernameOut(Schema):
    ok: bool
    display_name: str

_USERNAME_RE = re.compile(r'^[a-zA-Z0-9_]{2,30}$')

@router.get("/config/", response=ServerConfigOut, auth=None)
def server_config(request):
    """
    Returns the public server URL (NEURALOPS_SERVER_URL env var) and this
    server's version. Used by the frontend so users know what address to
    share, and (as of #170) to preview a saved server's version before
    connecting. No authentication required.
    """
    return {
        "server_url": getattr(settings, "NEURALOPS_SERVER_URL", ""),
        "server_version": getattr(settings, "NEURALOPS_VERSION", "unknown"),
        **read_module_versions(),
    }

# ── Supabase JWT sign-in ─────────────────────────────────────────────────────

@router.post("/signin", response=SignInResponse)
def signin(request, payload: SignInRequest):
    try:
        return signin_with_supabase_token(payload.access_token)
    except (SignInError, SupabaseTokenError) as exc:
        raise HttpError(401, str(exc))

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

# ── Public invite preview (no auth — called by portal invite page) ──────────

@router.get("/invite-preview/", response=InvitePreviewOut, auth=None)
def invite_preview(request, token: str):
    """
    Public endpoint — no auth required.
    Called by the portal invite page to show invite details before the user logs in.
    """
    import hashlib
    from nucleus.models import Invitation
    from django.utils import timezone

    token_hash = hashlib.sha256(token.encode()).hexdigest()
    invitation = Invitation.objects.filter(
        token_hash=token_hash,
        status=Invitation.Status.PENDING,
        is_active=True,
    ).select_related("company", "invited_by").first()

    if not invitation:
        raise HttpError(404, "Invite link is invalid or has already been used.")

    if invitation.expires_at and invitation.expires_at < timezone.now():
        raise HttpError(410, "This invite link has expired.")

    inviter_name = ""
    if invitation.invited_by:
        inviter_name = invitation.invited_by.get_display_name() or invitation.invited_by.email or ""

    return {
        "company_name": invitation.company.name if invitation.company else "NeuralOps Server",
        "inviter_name": inviter_name,
        "email": invitation.email,
        "expires_at": invitation.expires_at.isoformat() if invitation.expires_at else None,
    }

# ── Change display name ───────────────────────────────────────────────────────

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


# ── Effective permissions ────────────────────────────────────────────────────

@me_router.get("/permissions/", response=MyPermissionsOut)
def my_permissions_view(request):
    """
    Every right the caller holds, resolved for reach and keyed by object.
    The frontend gates each control on this instead of the company role.
    """
    from nucleus.models import Company

    company = Company.objects.filter(is_active=True).first()
    if not company:
        raise HttpError(503, "Server not initialised. Run 'python manage.py create_owner' first.")

    return my_permissions(request.auth, company)


# ── Role rights administration ───────────────────────────────────────────────

def _require_role_editor(request):
    """
    The company, and the caller's permission to edit what a role grants.

    Gated on the `role.update` right rather than a role name, like every other
    check in the app. Only Owner holds it: Owner's bundle is the whole registry
    and it is deliberately absent from the Admin/Member/Viewer bundles.

    can() raises on an unregistered code, which is what a server that has not
    re-run seed_permissions since this right was added would hit. That is a
    deployment step, not a permission failure, so it is reported as one.
    """
    from nucleus.models import Company

    company = Company.objects.filter(is_active=True).first()
    if not company:
        raise HttpError(503, "Server not initialised. Run 'python manage.py create_owner' first.")
    try:
        allowed = PermissionChecker.can(request.auth, "role.update", company=company)
    except ValueError:
        raise HttpError(
            503,
            "This server hasn't registered the role.update right yet. "
            "Run 'python manage.py seed_permissions'.",
        )
    if not allowed:
        raise HttpError(403, "Only the workspace owner can change what a role grants.")
    return company


@roles_router.get("/", response=RolesOut)
def roles(request):
    """The rights registry and what each role currently grants."""
    return list_roles(_require_role_editor(request))


@roles_router.patch("/{role_id}/rights/", response=SetRoleRightsOut)
def update_role_rights(request, role_id: str, payload: SetRoleRightsIn):
    """
    Replace the full right set of one role. Takes effect for every holder
    immediately -- RoleRight rows are what PermissionChecker reads, and nothing
    is copied per user.
    """
    company = _require_role_editor(request)
    try:
        return set_role_rights(company, role_id, payload.rights)
    except RoleEditError as exc:
        raise HttpError(400, str(exc))


# ── Profile photo ────────────────────────────────────────────────────────────

class AvatarOut(Schema):
    # Server-relative, like every other avatar the API returns; the client
    # resolves it against the connected server (absolutizeMedia).
    avatar: Optional[str] = None


@me_router.post("/avatar/", response=AvatarOut)
def upload_avatar(request, file: UploadedFile = File(...)):
    """
    Replace the caller's photo. The upload is decoded and re-encoded server
    side -- see set_profile_photo -- so nothing the client says about the file
    is taken at face value.
    """
    try:
        return {"avatar": set_profile_photo(request.auth, file)}
    except AvatarError as exc:
        raise HttpError(400, str(exc))


@me_router.delete("/avatar/", response=AvatarOut)
def delete_avatar(request):
    """Drop a custom photo and fall back to a server-assigned default."""
    return {"avatar": clear_profile_photo(request.auth)}


# =============================================================================
# Step 4 (docs/NUCLEUS-REVAMP.md) — first-run setup + local (offline) sign-in
# =============================================================================

from asgiref.sync import async_to_sync

from chat.stop_signals import signal_store


class SetupStatusOut(Schema):
    needs_owner: bool
    local_login_enabled: bool
    portal_url: str


class SetupStartOut(Schema):
    code: str          # what the install shows; the person types it at the portal
    request_id: str    # what the app passes back to /setup/poll/
    portal_url: str
    expires_in: int    # seconds the code stays valid


class SetupPollIn(Schema):
    request_id: str
    workspace_name: Optional[str] = None


class SetupPollOut(Schema):
    status: str                          # "pending" | "claimed"
    email: Optional[str] = None
    workspace: Optional[str] = None
    access_token: Optional[str] = None   # the Supabase token — the app's session


class LocalSignInIn(Schema):
    email: str
    password: str


class LocalSignInOut(Schema):
    access_token: str
    token_type: str
    expires_hours: int
    user: LocalUserOut


class SetPasswordIn(Schema):
    password: str


class ResetPasswordIn(Schema):
    user_id: str
    password: str


class OkOut(Schema):
    ok: bool


# A modest brake on password guessing: N tries per window, per address+email,
# counted in the same store the stop signals use (Redis across workers; the
# memory store in tests). Not a fortress — just enough that guessing is slow.
SIGNIN_ATTEMPT_LIMIT = 10
SIGNIN_ATTEMPT_WINDOW_SECONDS = 300


def _too_many_attempts(request, email: str) -> bool:
    address = request.META.get("REMOTE_ADDR", "") or "unknown"
    key = f"nx:signin:{address}:{(email or '').strip().lower()}"
    count = async_to_sync(signal_store().incr)(key, SIGNIN_ATTEMPT_WINDOW_SECONDS)
    return count > SIGNIN_ATTEMPT_LIMIT


# ── First-run setup: the install claims its owner ────────────────────────

@router.get("/setup/status/", response=SetupStatusOut, auth=None)
def setup_status(request):
    """Public: is this a fresh, unclaimed install? The app shows the setup screen on true."""
    return {
        "needs_owner": server_needs_owner(),
        "local_login_enabled": bool(getattr(settings, "LOCAL_LOGIN_ENABLED", True)),
        "portal_url": settings.NEURALOPS_PORTAL_URL,
    }


@router.post("/setup/start/", response=SetupStartOut, auth=None)
def setup_start(request):
    """
    Public, but only answers while the server has no owner. Asks the portal
    for a short code; the person signs in at portal_url and types the code
    there; the installer/app then polls /setup/poll/ until it is claimed.
    """
    if not server_needs_owner():
        raise HttpError(409, "This server already has an owner.")
    try:
        out = request_device_code()
    except PortalError as exc:
        raise HttpError(
            502,
            f"{exc} You can still claim this server from its terminal: "
            "python manage.py create_owner",
        )
    return {**out, "portal_url": settings.NEURALOPS_PORTAL_URL}


@router.post("/setup/poll/", response=SetupPollOut, auth=None)
def setup_poll(request, payload: SetupPollIn):
    """
    One poll of the portal. "pending" while nobody typed the code; once the
    portal hands back a token, the token is VERIFIED (same check as every
    sign-in) and that person becomes the owner — first verified claim wins.
    """
    if not server_needs_owner():
        raise HttpError(409, "This server already has an owner.")
    try:
        result = poll_device_code(payload.request_id)
    except PortalError as exc:
        raise HttpError(502, str(exc))
    if result["status"] != "claimed":
        return {"status": "pending"}
    try:
        claims = verify_supabase_token(result["access_token"])
    except SupabaseTokenError as exc:
        raise HttpError(401, f"The portal returned a token this server can't verify: {exc}")
    try:
        user, company = claim_install(claims, payload.workspace_name)
    except SetupError as exc:
        raise HttpError(409, str(exc))
    return {
        "status": "claimed",
        "email": user.email,
        "workspace": company.name,
        # The same Supabase token the person signed in with at the portal —
        # handed back so the app keeps it as its session, exactly as if they
        # had gone through /auth/signin.
        "access_token": result["access_token"],
    }


# ── Local (offline) sign-in ──────────────────────────────────────────

@router.post("/local/signin/", response=LocalSignInOut, auth=None)
def local_signin_view(request, payload: LocalSignInIn):
    """Email + local password → a local token (HS256, this server's SECRET_KEY)."""
    if not getattr(settings, "LOCAL_LOGIN_ENABLED", True):
        raise HttpError(403, "Offline sign-in is turned off on this server (LOCAL_LOGIN_ENABLED).")
    if _too_many_attempts(request, payload.email):
        raise HttpError(429, "Too many sign-in attempts. Wait a few minutes and try again.")
    try:
        return local_signin(payload.email, payload.password)
    except LocalSignInError as exc:
        raise HttpError(401, str(exc))


@router.post("/local/set-password/", response=OkOut, auth=SupabaseBearer())
def set_local_password_view(request, payload: SetPasswordIn):
    """Any signed-in person sets their OWN offline password (profile screen)."""
    try:
        set_local_password(request.auth, payload.password)
    except LocalSignInError as exc:
        raise HttpError(400, str(exc))
    return {"ok": True}


@router.post("/local/reset-password/", response=OkOut, auth=SupabaseBearer())
def reset_local_password_view(request, payload: ResetPasswordIn):
    """Set someone ELSE's offline password — gated on company.local_password."""
    from django.contrib.auth import get_user_model
    from nucleus.models import Company

    company = Company.objects.filter(is_active=True).first()
    if not company:
        raise HttpError(503, "Server not initialised.")
    try:
        allowed = PermissionChecker.can(request.auth, "company.local_password", company=company)
    except ValueError:
        raise HttpError(
            503,
            "This server hasn't registered the company.local_password right yet. "
            "Run 'python manage.py seed_permissions'.",
        )
    if not allowed:
        raise HttpError(403, "Only an owner or admin can reset someone's offline password.")

    target = get_user_model().objects.filter(
        id=payload.user_id, is_active=True, user_type="human",
    ).first()
    if not target:
        raise HttpError(404, "No such user on this server.")
    try:
        set_local_password(target, payload.password)
    except LocalSignInError as exc:
        raise HttpError(400, str(exc))
    return {"ok": True}
