import logging
import random
import re
import secrets

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

    import random
    from pathlib import Path
    from django.conf import settings

    kind = "persona" if user.user_type == User.UserType.PERSONA else "human"
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
# Role rights administration (GET/PATCH /api/v1/roles/)
# =========================================================

# Editing a role changes what every holder of it can do, at once -- that is the
# point of role-level rights, and why these two invariants are enforced on the
# server rather than left to the UI.
#
# 1. The Owner role is never editable and always holds the whole registry.
#    Without this an owner can narrow themselves out of their own workspace
#    with no way back in.
# 2. Member management stays Owner/Admin-only, always. The two rights below can
#    be REMOVED from any role, but never GRANTED to one outside that tier.
OWNER_ROLE_NAME = "Owner"
ADMIN_ROLE_NAME = "Admin"
MEMBER_MANAGEMENT_RIGHTS = frozenset({"company.invite_member", "company.remove_member"})


class RoleEditError(Exception):
    """A refused role edit. The API turns this into a 400/403 with the text."""


def list_roles(company) -> dict:
    """
    The rights registry and what each role currently grants -- the matrix the
    permissions screen renders.

    Registry entries carry `scope` (the narrowest level the right can be
    granted at) and `object_type`, which is what groups the table. Both come
    straight from the Right rows seed_permissions wrote, not from a second copy
    in the client.
    """
    from authn.permissions.models import Right, Role, RoleRight

    rights = list(Right.objects.all().order_by("object_type", "code"))
    roles = list(Role.objects.filter(company=company).order_by("name"))
    held = {}
    for role_id, code in RoleRight.objects.filter(
        role__company=company
    ).values_list("role_id", "right__code"):
        held.setdefault(role_id, set()).add(code)

    return {
        "rights": [
            {
                "code": r.code,
                "object_type": r.object_type,
                "scope": r.scope,
                "description": r.description,
            }
            for r in rights
        ],
        "roles": [
            {
                "id": str(role.id),
                "name": role.name,
                "scope": role.scope,
                "description": role.description,
                "rights": sorted(held.get(role.id, set())),
                # The client renders these read-only rather than deciding the
                # rule itself -- see the invariants above.
                "editable": role.name != OWNER_ROLE_NAME,
                "locked_rights": (
                    [] if role.name in (OWNER_ROLE_NAME, ADMIN_ROLE_NAME)
                    else sorted(MEMBER_MANAGEMENT_RIGHTS)
                ),
            }
            for role in roles
        ],
    }


@transaction.atomic
def set_role_rights(company, role_id: str, codes: list) -> dict:
    """
    Replace the full right set of one role. Full-set replace, not a delta: the
    screen sends what the role should grant, and the difference is applied.

    Refuses, with the reason:
      - an unknown role, or one belonging to another company
      - the Owner role, which always holds everything
      - granting a member-management right to a role outside the Owner/Admin
        tier (removing one is always allowed)
      - an unregistered right code, which would otherwise create a row that
        can() then raises on
    """
    from authn.permissions.models import Right, Role, RoleRight

    role = Role.objects.filter(company=company, id=role_id).first()
    if role is None:
        raise RoleEditError("That role doesn't exist on this server.")
    if role.name == OWNER_ROLE_NAME:
        raise RoleEditError(
            "The Owner role always holds every right and can't be edited."
        )

    wanted = set(codes)
    known = {r.code: r for r in Right.objects.all()}
    unknown = sorted(wanted - set(known))
    if unknown:
        raise RoleEditError(
            f"Unknown right code(s): {', '.join(unknown)}. "
            "Run manage.py seed_permissions if the registry changed."
        )

    if role.name != ADMIN_ROLE_NAME:
        current = set(
            RoleRight.objects.filter(role=role).values_list("right__code", flat=True)
        )
        # Only newly GRANTED ones are refused -- a role that somehow already
        # holds one can still have it taken away.
        added = (wanted & MEMBER_MANAGEMENT_RIGHTS) - current
        if added:
            raise RoleEditError(
                f"{role.name} can't be given {', '.join(sorted(added))} — "
                "managing members stays with Owner and Admin."
            )

    current_rows = {
        code: rid
        for rid, code in RoleRight.objects.filter(role=role).values_list("id", "right__code")
    }
    to_add = wanted - set(current_rows)
    to_remove = set(current_rows) - wanted

    if to_remove:
        RoleRight.objects.filter(id__in=[current_rows[c] for c in to_remove]).delete()
    if to_add:
        RoleRight.objects.bulk_create(
            [RoleRight(role=role, right=known[c]) for c in sorted(to_add)]
        )

    logger.info(
        "[roles] %s rights updated: +%d -%d (now %d)",
        role.name, len(to_add), len(to_remove), len(wanted),
    )
    return {
        "id": str(role.id),
        "name": role.name,
        "rights": sorted(wanted),
        "added": sorted(to_add),
        "removed": sorted(to_remove),
    }


# =========================================================
# Profile photo (POST/DELETE /api/v1/me/avatar/)
# =========================================================

# Uploads are user-supplied bytes, so nothing about the request is trusted:
# not the filename, not the content type, not the extension. The file is
# decoded with Pillow, re-encoded, and written under a name the server picks.
AVATAR_MAX_BYTES = 5 * 1024 * 1024   # 5 MB, checked before decoding
AVATAR_MAX_EDGE = 512                # px; larger is pointless for a 40px circle
AVATAR_DIR = "avatars/custom"


class AvatarError(Exception):
    """A refused upload. The API turns this into a 400 with the text."""


def set_profile_photo(user, upload) -> str:
    """
    Replace `user`'s photo with an uploaded image and return its path.

    Re-encoding rather than storing the bytes as sent is the point: it proves
    the file really is an image, drops EXIF (which carries GPS among other
    things), and means a polyglot -- something that is a valid image AND a
    valid script -- cannot survive the round trip. The stored name is derived
    from the user id, never from the upload, so a crafted filename cannot
    traverse or collide.
    """
    from io import BytesIO
    from django.core.files.base import ContentFile
    from django.core.files.storage import default_storage
    from PIL import Image, UnidentifiedImageError

    size = getattr(upload, "size", None)
    if size is not None and size > AVATAR_MAX_BYTES:
        raise AvatarError(
            f"That image is {size // (1024 * 1024)} MB. Please use one under "
            f"{AVATAR_MAX_BYTES // (1024 * 1024)} MB."
        )

    try:
        upload.seek(0)
        image = Image.open(upload)
        image.load()  # force a real decode; verify() alone leaves it unusable
    except (UnidentifiedImageError, OSError, ValueError):
        raise AvatarError("That file isn't an image we can read. Try a PNG or JPEG.")

    # Flatten to RGB on white: a transparent PNG would otherwise go black once
    # saved as JPEG, and RGBA/P modes cannot be saved as JPEG at all.
    if image.mode in ("RGBA", "LA", "P"):
        flattened = Image.new("RGB", image.size, (255, 255, 255))
        rgba = image.convert("RGBA")
        flattened.paste(rgba, mask=rgba.split()[-1])
        image = flattened
    elif image.mode != "RGB":
        image = image.convert("RGB")

    image.thumbnail((AVATAR_MAX_EDGE, AVATAR_MAX_EDGE))

    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=88, optimize=True)

    # A fresh name each time, so a cached old photo is never served for a new
    # one and the previous file can be deleted without racing the new write.
    #
    # Written through storage directly rather than user.avatar.save(), which
    # would prepend the field's upload_to ("avatars/%Y/%m/") and bury the file
    # somewhere clear_profile_photo cannot recognise. assign_avatar() sets
    # .name the same way for the same reason.
    name = f"{AVATAR_DIR}/{user.id}-{secrets.token_hex(4)}.jpg"
    previous = user.avatar.name if user.avatar else None
    stored = default_storage.save(name, ContentFile(buffer.getvalue()))
    user.avatar.name = stored
    user.save(update_fields=["avatar"])

    if previous and previous.startswith(f"{AVATAR_DIR}/"):
        _delete_stored_avatar(previous)

    logger.info("[avatar] %s set a profile photo", user.email)
    return stored


def clear_profile_photo(user) -> str | None:
    """
    Drop a custom photo and fall back to a server-assigned one.

    Returns the path now in use, or None when no pool has been seeded -- the UI
    renders initials for an empty avatar either way.
    """
    previous = user.avatar.name if user.avatar else None
    user.avatar = ""
    user.save(update_fields=["avatar"])

    if previous and previous.startswith(f"{AVATAR_DIR}/"):
        _delete_stored_avatar(previous)

    # Straight back to a default rather than leaving them blank until their
    # next sign-in, which is when assign_avatar() would otherwise run.
    return assign_avatar(user)


def _delete_stored_avatar(path: str) -> None:
    """Best effort -- a leftover file is untidy, not a failure worth raising."""
    from pathlib import Path
    from django.conf import settings

    try:
        target = (Path(settings.MEDIA_ROOT) / path).resolve()
        media_root = Path(settings.MEDIA_ROOT).resolve()
        # Never follow a path that escapes MEDIA_ROOT, whatever produced it.
        if media_root in target.parents and target.is_file():
            target.unlink()
    except OSError as exc:
        logger.warning("[avatar] could not remove %s: %s", path, exc)


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
