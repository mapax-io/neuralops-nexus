import logging

import httpx
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from .supabase import SupabaseTokenError, verify_supabase_token

logger = logging.getLogger(__name__)

User = get_user_model()


# =========================================================
# Existing: Supabase JWT sign-in (portal / web flow)
# =========================================================

class SignInError(Exception):
    pass


@transaction.atomic
def signin_with_supabase_token(access_token: str) -> dict:
    if not access_token:
        raise SignInError("access_token is required.")

    claims = verify_supabase_token(access_token)

    email = claims.get("email")
    supabase_user_id = claims.get("sub")
    email_verified = claims.get("email_verified", False)

    if not email:
        raise SignInError("Email is missing from Supabase token.")

    user, created = User.objects.get_or_create(
        email=email,
        defaults={"username": email, "is_active": True},
    )

    changed_fields = []
    if not user.username:
        user.username = email
        changed_fields.append("username")
    if not user.is_active:
        user.is_active = True
        changed_fields.append("is_active")
    if changed_fields:
        user.save(update_fields=changed_fields)

    return {
        "user": {
            "id": str(user.id),
            "email": user.email,
            "username": user.username,
            "is_new_user": created,
        },
        "external_identity": {
            "provider": "supabase",
            "provider_user_id": supabase_user_id,
            "email": email,
            "email_verified": email_verified,
        },
    }


# =========================================================
# Server connection verify
# =========================================================

@transaction.atomic
def auth_verify(access_token: str) -> dict:
    """
    Called by GET /api/v1/auth/verify/

    1. Verifies the Supabase JWT
    2. Gets or creates the local Django user
    3. Checks company + membership status
    4. Returns ok + user info + company info

    Raises:
        SupabaseTokenError — if JWT is invalid
        PermissionError   — if user is not allowed on this server
    """
    from nucleus.models import Company, CompanyAccess

    claims = verify_supabase_token(access_token)

    email = claims.get("email")
    if not email:
        raise SupabaseTokenError("Email missing from token.")

    user, created = User.objects.get_or_create(
        email=email,
        defaults={"username": email, "is_active": True},
    )

    if not user.is_active:
        raise PermissionError("Your account is not active on this server.")

    # ── Company check ──────────────────────────────────────────────────────
    company = Company.objects.filter(is_active=True).first()

    if not company:
        # No company set up yet — server is unconfigured
        logger.info("[auth_verify] no company found, server needs setup. user=%s", email)
        return {
            "ok": True,
            "email": user.email,
            "user_id": str(user.id),
            "is_new_user": created,
            "company_exists": False,
            "is_owner": False,
            "role": None,
            "company_name": None,
        }

    # ── Membership check ───────────────────────────────────────────────────
    try:
        access = CompanyAccess.objects.get(company=company, user=user, is_active=True)
    except CompanyAccess.DoesNotExist:
        raise PermissionError("You are not a member of this server. Ask the owner to invite you.")

    # ── Update current_company if not set ──────────────────────────────────
    if user.current_company_id != company.id:
        user.current_company = company
        user.save(update_fields=["current_company"])

    is_owner = access.role == CompanyAccess.Role.OWNER

    logger.info("[auth_verify] user=%s role=%s company=%s", email, access.role, company.name)

    return {
        "ok": True,
        "email": user.email,
        "user_id": str(user.id),
        "is_new_user": created,
        "company_exists": True,
        "is_owner": is_owner,
        "role": access.role,
        "company_name": company.name,
    }


# =========================================================
# Device activation flow
# =========================================================

class DeviceAuthError(Exception):
    pass


def _register_device_in_supabase(device_id: str) -> None:
    try:
        response = httpx.post(
            settings.SUPABASE_DEVICE_REQUEST_URL,
            json={"device_id": device_id, "device_name": "NeuralOps Desktop"},
            headers={
                "Authorization": f"Bearer {settings.SUPABASE_ANON_KEY}",
                "X-NeuralOps-Token": settings.NEURALOPS_INSTALL_TOKEN,
                "Content-Type": "application/json",
            },
            timeout=15,
        )
        response.raise_for_status()
        logger.info("[device_auth] Registered device_id=%s with Supabase", device_id)
    except httpx.HTTPStatusError as exc:
        raise DeviceAuthError(
            f"Supabase device-request returned {exc.response.status_code}: {exc.response.text}"
        ) from exc
    except Exception as exc:
        raise DeviceAuthError(f"Failed to reach Supabase: {exc}") from exc


def auth_init() -> dict:
    from .models import DeviceSession
    from .tasks import poll_device_activation

    session = DeviceSession.objects.first()

    if session and session.status == DeviceSession.STATUS_ACTIVE:
        if session.session_expires_at and session.session_expires_at > timezone.now():
            return {
                "status": "authenticated",
                "email": session.email,
                "user_id": session.user_id,
                "session_expires_at": session.session_expires_at.isoformat(),
            }
        else:
            session.status = DeviceSession.STATUS_EXPIRED
            session.save(update_fields=["status", "updated_at"])

    if session and session.status == DeviceSession.STATUS_PENDING:
        login_url = f"{settings.NEURALOPS_PORTAL_URL}/login?device_id={session.device_id}"
        return {"status": "unauthenticated", "login_url": login_url}

    if session:
        device_id = str(session.device_id)
        _register_device_in_supabase(device_id)
        session.status = DeviceSession.STATUS_PENDING
        session.user_id = None
        session.email = None
        session.session_expires_at = None
        session.celery_task_id = None
        session.save()
    else:
        session = DeviceSession.objects.create()
        device_id = str(session.device_id)
        _register_device_in_supabase(device_id)

    task = poll_device_activation.delay(device_id)
    session.celery_task_id = task.id
    session.save(update_fields=["celery_task_id", "updated_at"])

    login_url = f"{settings.NEURALOPS_PORTAL_URL}/login?device_id={device_id}"
    return {"status": "unauthenticated", "login_url": login_url}


def auth_status() -> dict:
    from .models import DeviceSession

    session = DeviceSession.objects.first()
    if not session:
        return {"status": "pending"}

    if session.status == DeviceSession.STATUS_ACTIVE:
        if session.session_expires_at and session.session_expires_at > timezone.now():
            return {
                "status": "active",
                "email": session.email,
                "user_id": session.user_id,
                "session_expires_at": session.session_expires_at.isoformat(),
            }
        else:
            session.status = DeviceSession.STATUS_EXPIRED
            session.save(update_fields=["status", "updated_at"])
            return {"status": "session_expired"}

    if session.status == DeviceSession.STATUS_EXPIRED:
        return {"status": "session_expired"}

    return {"status": "pending"}
