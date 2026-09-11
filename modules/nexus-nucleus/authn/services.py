import logging
import random
import re

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from .supabase import SupabaseTokenError, verify_supabase_token
from .versions import read_module_versions

logger = logging.getLogger(__name__)

User = get_user_model()


def assign_display_name(user) -> str:
    """
    Auto-assign a unique per-server display name on the User record.
    Derived from the local part of the user's email.
    If already taken by another user on this server, appends a random 2-digit number.
    """
    # Already has one — skip
    if user.display_name:
        return user.display_name

    # Derive base name from email local part, keep only alphanumeric + underscore
    base = (user.email or "").split("@")[0]
    base = re.sub(r"[^a-zA-Z0-9_]", "", base).lower() or "user"

    # Find a unique name on this server
    taken = set(
        User.objects.filter(is_active=True)
        .exclude(pk=user.pk)
        .values_list("display_name", flat=True)
    )

    candidate = base
    while candidate in taken:
        candidate = f"{base}_{random.randint(10, 99)}"

    user.display_name = candidate
    user.save(update_fields=["display_name"])
    return candidate


def assign_avatar(user) -> str | None:
    """
    Auto-assign a random avatar from the preset pool (see #148), mirroring
    assign_display_name()'s "skip if already set" idempotency.

    PERSONAS ONLY. Real people no longer get one: the human pool was DiceBear
    "avataaars", cartoon faces with hair, and handing them out at random put a
    face of the wrong apparent gender on real teammates. A picture of a person
    that is not them is worse than no picture, and there is nothing to derive a
    correct one from -- the server knows an email and a display name. So humans
    fall through to the initials the UI already renders when avatar is empty
    (message bubbles, the members list, the team dialog), which is accurate by
    construction. Personas keep theirs: "bottts" is a robot, which is what a
    persona is, and it carries no claim about a person.

    Pool must be pre-seeded once via `python manage.py seed_avatars`, which
    caches DiceBear-generated PNGs under MEDIA_ROOT/avatars/pool/<kind>/ --
    a different style for humans vs personas so identity type is visually
    distinguishable at a glance.

    Best-effort unique: prefers a pool file not already used by another
    active user, falling back to any pool file (allowing reuse) once the
    pool is exhausted -- uniqueness is a nice-to-have here, not enforced.

    Called for both real users (auth_verify(), on invite-accept and as a
    fallback) and personas (create_persona()'s shadow_user, since a persona
    is "the same as a User, just model-backed" -- see #148 discussion).

    Returns the assigned relative avatar path, or None if the pool hasn't
    been seeded yet / is empty for this user's kind.
    """
    # Already has one — skip
    if user.avatar:
        return user.avatar.name

    if user.user_type != User.UserType.PERSONA:
        return None

    import random
    from pathlib import Path
    from django.conf import settings

    kind = "persona"
    pool_dir = Path(settings.MEDIA_ROOT) / "avatars" / "pool" / kind

    if not pool_dir.is_dir():
        logger.warning(
            "[assign_avatar] pool dir missing: %s -- run `python manage.py seed_avatars` first",
            pool_dir,
        )
        return None

    available = sorted(p.name for p in pool_dir.glob("*.png"))
    if not available:
        logger.warning("[assign_avatar] pool dir empty: %s", pool_dir)
        return None

    taken = set(
        User.objects.filter(is_active=True, avatar__startswith=f"avatars/pool/{kind}/")
        .exclude(pk=user.pk)
        .values_list("avatar", flat=True)
    )
    unused = [f for f in available if f"avatars/pool/{kind}/{f}" not in taken]
    chosen = random.choice(unused) if unused else random.choice(available)

    user.avatar.name = f"avatars/pool/{kind}/{chosen}"
    user.save(update_fields=["avatar"])
    return user.avatar.name


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
        from django.conf import settings as dj_settings
        return {
            "ok": True,
            "email": user.email,
            "user_id": str(user.id),
            "is_new_user": created,
            "company_exists": False,
            "is_owner": False,
            "role": None,
            "company_name": None,
            "server_version": dj_settings.NEURALOPS_VERSION,
            **read_module_versions(),
        }

    # ── Membership check ───────────────────────────────────────────────────
    from nucleus.models import Invitation
    from django.contrib.auth.models import Group
    from django.utils import timezone

    access = CompanyAccess.objects.filter(company=company, user=user, is_active=True).first()

    if not access:
        # Check if there's a pending invitation for this email
        invitation = Invitation.objects.filter(
            company=company,
            email=email,
            status=Invitation.Status.PENDING,
            is_active=True,
        ).first()

        if not invitation:
            raise PermissionError("You are not a member of this server. Ask the owner to invite you.")

        # Check invitation not expired
        if invitation.expires_at and invitation.expires_at < timezone.now():
            invitation.status = Invitation.Status.EXPIRED
            invitation.save(update_fields=["status", "updated_at"])
            raise PermissionError("Your invitation has expired. Ask the owner to invite you again.")

        # Accept invitation — create CompanyAccess
        access = CompanyAccess.objects.create(
            company=company,
            user=user,
            role=invitation.role,
            invited_by=invitation.invited_by,
        )
        assign_display_name(user)
        assign_avatar(user)

        # Real permission grant -- CompanyAccess above is just the legacy
        # "is this person a member" flag; PermissionChecker only ever reads
        # RoleAssignment. Without this, an accepted invite still leaves the
        # person with zero real rights. See #120.
        from authn.permissions.checker import PermissionChecker
        from authn.permissions.models import Role
        company_role = Role.objects.filter(company=company, name=invitation.role.capitalize()).first()
        if company_role:
            PermissionChecker.assign_role(user, company_role, company, granted_by=invitation.invited_by)

        # Add to corresponding Django group
        try:
            group = Group.objects.get(name=invitation.role.capitalize())
            user.groups.add(group)
        except Group.DoesNotExist:
            pass

        # Mark invitation as accepted
        invitation.status = Invitation.Status.ACCEPTED
        invitation.accepted_at = timezone.now()
        invitation.save(update_fields=["status", "accepted_at", "updated_at"])

        # Add to the project they were invited from
        _add_user_to_invited_project(company, user, invitation)

        logger.info("[auth_verify] invitation accepted user=%s role=%s", email, invitation.role)

    # ── Assign display name if not yet set ────────────────────────────────
    assign_display_name(user)
    assign_avatar(user)

    # ── Update current_company if not set ──────────────────────────────────
    if user.current_company_id != company.id:
        user.current_company = company
        user.save(update_fields=["current_company"])

    is_owner = access.role == CompanyAccess.Role.OWNER

    logger.info("[auth_verify] user=%s role=%s company=%s", email, access.role, company.name)

    from django.conf import settings as dj_settings
    return {
        "ok": True,
        "email": user.email,
        "user_id": str(user.id),
        "is_new_user": created,
        "company_exists": True,
        "is_owner": is_owner,
        "role": access.role,
        "company_name": company.name,
        "server_version": dj_settings.NEURALOPS_VERSION,
        **read_module_versions(),
    }


# =========================================================
# Effective permissions (GET /api/v1/me/permissions/)
# =========================================================

def my_permissions(user, company) -> dict:
    """
    Every right `user` holds, resolved for reach and keyed by the object it
    applies to -- the payload the frontend gates its controls on.

    Each list is already resolved: a project's entry includes rights inherited
    from a company assignment, a topic's includes rights inherited from its
    project or company. The client answers "may I?" with a set lookup and never
    walks the scope hierarchy itself -- reach rules stay here, in one place.

    Only objects the user can reach appear as keys; an absent key means no
    rights there. A topic reachable ONLY through a project- or company-scope
    assignment still gets a key, so a project admin keeps their topic-scoped
    controls (topic.update/archive, persona.mention, session.*, schedule.*).

    Resolves every visible object in a fixed number of queries: the row_rules
    walk to find them, then two batched lookups each for projects and topics
    (PermissionChecker.rights_for_many) -- not two per object.
    """
    from authn.permissions.checker import PermissionChecker
    from authn.permissions.row_rules import visible_channels, visible_projects, visible_topics

    visible_project_rows = list(visible_projects(user, company))
    visible_topic_rows = [
        topic
        for project in visible_project_rows
        for channel in visible_channels(user, project)
        for topic in visible_topics(user, channel)
    ]

    project_rights = PermissionChecker.rights_for_many(user, visible_project_rows)
    topic_rights = PermissionChecker.rights_for_many(user, visible_topic_rows)

    return {
        "company": {
            "id": str(company.id),
            "rights": sorted(PermissionChecker.rights_for(user, company=company)),
        },
        "projects": {key: sorted(codes) for key, codes in project_rights.items()},
        "topics": {key: sorted(codes) for key, codes in topic_rights.items()},
    }


# =========================================================
# Invitation helper
# =========================================================

def _add_user_to_invited_project(company, user, invitation):
    """
    Finish the project/topic half of an accepted invite.

    Reads what was promised in invitation.access_payload -- stashed by
    workspace/services.py:invite_to_project() when this person was brand
    new -- and grants BOTH the legacy row (ProjectMember/TopicParticipant)
    AND the real RoleAssignment the RBAC system checks. Mirrors the
    existing-member path inside invite_to_project() itself, step for
    step. If access_payload has no project_id, this was a system-only
    invite (e.g. POST /members/invite/) -- nothing more to grant. See #120.
    """
    from nucleus.models import Project, ProjectMember, ChatTopic
    from authn.permissions.checker import PermissionChecker
    from authn.permissions.models import Role
    from workspace.services import _add_to_topic

    payload = invitation.access_payload or {}
    project_id = payload.get("project_id")
    if not project_id:
        return

    project = Project.objects.filter(id=project_id, company=company, is_active=True).first()
    if not project:
        return

    member, _ = ProjectMember.objects.get_or_create(
        company=company, project=project, user=user,
        defaults={"role": invitation.role},
    )
    if not member.is_active:
        member.is_active = True
        member.save(update_fields=["is_active"])

    project_role = Role.objects.filter(company=company, name=invitation.role.capitalize()).first()
    scope = payload.get("scope", "project")
    topic_id = payload.get("topic_id")

    if scope == "topic" and topic_id:
        _add_to_topic(company, project, topic_id, user, invitation.role)
        topic = ChatTopic.objects.filter(
            company=company, project=project, id=topic_id, is_active=True
        ).first()
        if topic and project_role:
            PermissionChecker.assign_role(user, project_role, topic, granted_by=invitation.invited_by)
    elif project_role:
        PermissionChecker.assign_role(user, project_role, project, granted_by=invitation.invited_by)

    logger.info("[invite] user=%s added to project=%s (scope=%s)", user.email, project.name, scope)


# =========================================================
# Device activation flow — REMOVED
# =========================================================
# auth_init(), auth_status(), DeviceAuthError, and _register_device_in_supabase()
# used to live here. Removed: the frontend never called /auth/init/ or
# /auth/status/ — it signs in via Supabase directly and calls auth_verify()
# (above) instead. See git history to revive if device-poll login is needed
# later (e.g. a CLI client without a browser).
