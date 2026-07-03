import hashlib

from django.conf import settings
from django.utils import timezone
from ninja import Router, Schema
from ninja.errors import HttpError

from .schema import AuthInitResponse, AuthStatusResponse, AuthVerifyResponse, SignInRequest, SignInResponse
from .services import DeviceAuthError, SignInError, auth_init, auth_status, auth_verify, signin_with_supabase_token
from .supabase import SupabaseTokenError
from .team_schema import InviteInfoOut
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
    Used by the frontend to auto-populate the server address in invite emails.
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
    Called by the React app when the user clicks Connect on a server.
    Verifies the Supabase JWT and checks if the user is allowed on this server.
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


# ── Invite link info (public — no auth) ─────────────────────────────────────────

@router.get("/invite/info/", response=InviteInfoOut, auth=None)
def invite_info(request, token: str):
    """
    Public endpoint. Returns metadata about a pending invite so the
    /join page can show 'You have been invited by X to join this server.'
    """
    from nucleus.models import Invitation

    token_hash = hashlib.sha256(token.encode()).hexdigest()
    inv = Invitation.objects.filter(
        token_hash=token_hash,
        status=Invitation.Status.PENDING,
        is_active=True,
    ).select_related("invited_by", "invited_by__human_profile").first()

    if not inv:
        raise HttpError(404, "Invitation not found or already used.")

    if inv.expires_at and inv.expires_at < timezone.now():
        raise HttpError(410, "This invitation link has expired. Ask the sender to resend it.")

    inviter_profile = getattr(inv.invited_by, "human_profile", None)
    inviter_name = (
        inviter_profile.full_name if inviter_profile and inviter_profile.full_name
        else inv.invited_by.email or str(inv.invited_by.id)
    )

    return {
        "email": inv.email,
        "invited_by": inviter_name,
        "server_url": getattr(settings, "NEURALOPS_SERVER_URL", ""),
        "expires_at": inv.expires_at.isoformat() if inv.expires_at else "",
    }


# ── Invite link redeem (requires Supabase JWT) ─────────────────────────────

from .auth import SupabaseBearer  # noqa: E402 (below other imports to avoid circular)


class RedeemInviteRequest(Schema):
    token: str


class RedeemInviteOut(Schema):
    ok: bool
    message: str


@router.post("/invite/redeem/", response=RedeemInviteOut, auth=SupabaseBearer())
def redeem_invite(request, payload: RedeemInviteRequest):
    """
    Called by the /join page after the user has signed in via Supabase.
    Looks up the invitation by token, adds the user to the project/topic,
    marks the invitation as accepted.
    """
    from nucleus.models import Invitation, CompanyAccess, ProjectMember

    token_hash = hashlib.sha256(payload.token.encode()).hexdigest()
    inv = Invitation.objects.filter(
        token_hash=token_hash,
        status=Invitation.Status.PENDING,
        is_active=True,
    ).select_related("company", "invited_by").first()

    if not inv:
        raise HttpError(404, "Invitation not found or already used.")

    if inv.expires_at and inv.expires_at < timezone.now():
        raise HttpError(410, "This invitation link has expired. Ask the sender to resend it.")

    user = request.auth

    # Ensure user belongs to the company (creates CompanyAccess if not)
    access = CompanyAccess.objects.filter(
        company=inv.company, user=user, is_active=True
    ).first()
    if not access:
        CompanyAccess.objects.create(
            company=inv.company,
            user=user,
            role=inv.role,
        )

    # Add to project (from access_payload)
    payload_data = inv.access_payload or {}
    project_id = payload_data.get("project_id")
    scope = payload_data.get("scope", "project")
    topic_id = payload_data.get("topic_id")

    if project_id:
        from nucleus.models import Project
        project = Project.objects.filter(
            id=project_id, company=inv.company, is_active=True
        ).first()
        if project:
            member = ProjectMember.objects.filter(
                company=inv.company, project=project, user=user
            ).first()
            if not member:
                ProjectMember.objects.create(
                    company=inv.company, project=project,
                    user=user, role=inv.role,
                )
            elif not member.is_active:
                member.is_active = True
                member.save(update_fields=["is_active"])

            if scope == "topic" and topic_id:
                team_svc._add_to_topic(inv.company, project, topic_id, user, inv.role)

    # Mark invitation accepted
    inv.status = Invitation.Status.ACCEPTED
    inv.save(update_fields=["status"])

    return {"ok": True, "message": "You have joined the workspace. Welcome to NeuralOps!"}
