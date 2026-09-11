"""
Business logic for Workspace (Projects, Channels, Topics), Members, and Team.
All queries are scoped to company — safe for multi-tenant use.
"""
import copy
import hashlib
import logging
import secrets
import uuid
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils import timezone
from django.utils.text import slugify

from authn.permissions.checker import PermissionChecker
from authn.permissions.models import Role, RoleAssignment
from authn.permissions.row_rules import (
    _reachable_project_ids, visible_channels, visible_projects, visible_topics,
)
from nucleus.models import (
    ChatMessage, ChatReadMarker, ChatTopic, Channel, Company, CompanyAccess,
    Invitation, Persona, Project, ProjectMember, TopicParticipant,
)
import os
from nucleus.models import MCPServer
logger = logging.getLogger(__name__)

User = get_user_model()


def get_company():
    # Company — imported at top of file.
    return Company.objects.filter(is_active=True).first()


# ── Projects ──────────────────────────────────────────────────────────────────

def list_projects(company, user, include_archived=False):
    # visible_projects — imported at top of file.
    return visible_projects(user, company, include_archived=include_archived)

# workspace/services.py

def get_project_folder_name(project) -> str:
    return f"{project.slug}-{str(project.id)[:8]}"

# Capabilities every new project is provisioned with, as INTERNAL MCPServer
# rows (pydantic-ai in-process, no protocol). This replaces the single
# external stdio row that used to spawn
# `npx -y @modelcontextprotocol/server-filesystem` -- pydantic-ai does
# filesystem access natively, so shelling out to a Node subprocess for it was
# a whole extra moving part serving no purpose.
#
# All four live in ONE row, as four keys of its capability_config -- which is
# the shape capability_config was built for (one JSON, many capability keys)
# and the shape nexus-ai reads. A persona mounts the row and gets all four.
#
# The trade-off, so it is a known one: there is no way to give a persona
# Filesystem without also giving it Shell. If that ever needs to be possible,
# split this into a row per capability -- the model already supports it, only
# this function would change.
DEFAULT_PROJECT_CAPABILITIES = ("filesystem", "shell", "web_search", "web_fetch")

# Capability keys whose value must point at THIS project's folder rather than
# the template's container-wide default of ".".
_PROJECT_SCOPED_KEYS = {
    "filesystem": "root_dir",
    "shell": "cwd",
}


def provision_project_folder_and_mcp(project):
    """
    Create the project's folder on disk and its default tool capabilities.

    Returns the single MCPServer row created. The folder is still needed even
    though nothing spawns a filesystem server any more -- it is what
    Filesystem.root_dir and Shell.cwd point at, and nexus-ai sees it at the
    same path because both containers bind-mount ./projects to /nexus/projects.
    """
    folder_name = get_project_folder_name(project)
    folder_path = os.path.join(settings.PROJECTS_ROOT, folder_name)
    os.makedirs(folder_path, exist_ok=True)

    capability_config = {}
    for capability in DEFAULT_PROJECT_CAPABILITIES:
        # Defaults come from the template so there is ONE source of truth for
        # them; only the path-bound key is overridden per project.
        config = copy.deepcopy(settings.MCP_CAPABILITY_TEMPLATE.get(capability, {}))
        scoped_key = _PROJECT_SCOPED_KEYS.get(capability)
        if scoped_key:
            config[scoped_key] = folder_path
        capability_config[capability] = config

    return MCPServer.objects.create(
        company=project.company,
        project=project,          # a real FK -- ownership set at creation
        name=f"{project.name} Capabilities",
        is_internal=True,
        capability_config=capability_config,
        # REQUIRED, not cosmetic: auth_type defaults to "static_secrets", and
        # the mcp_internal_has_no_endpoint constraint rejects any internal row
        # that is not "none". .objects.create() bypasses
        # intelligence/services.py's normalisation, so it has to be set by
        # hand here or every project creation dies on an IntegrityError.
        auth_type=MCPServer.AuthType.NONE,
        is_protected=True,        # not user-deletable
        is_default=True,
    )

def create_project(company, user, name: str, description: str = None):
    # Project, Channel, ProjectMember, Role, PermissionChecker — imported at top of file.

    slug = _unique_project_slug(company, name)

    project = Project.objects.create(
        company=company, name=name, slug=slug, description=description or "",
    )
    Channel.objects.create(
        company=company, project=project, name="general",
        slug="general", description="General discussion",
    )

    # Legacy membership record -- kept alongside the new RoleAssignment below
    # so untouched code that still reads ProjectMember directly (list_team,
    # add_member, invite_to_project, etc.) keeps working during migration.
    ProjectMember.objects.create(
        company=company, project=project, user=user, role=ProjectMember.Role.ADMIN,
    )

    # New permission system: creator becomes project-scoped Admin.
    # NOTE: fetched by name regardless of this Role row's own `scope` field --
    # seed_permissions currently seeds all four default roles at scope="company",
    # which is the still-open inconsistency flagged earlier (Role.scope forcing
    # one assignment level vs. the same Role being assignable at any scope).
    # Revisit once that's decided.
    admin_role = Role.objects.filter(company=company, name="Admin").first()
    if admin_role:
        PermissionChecker.assign_role(user, admin_role, project, granted_by=user)

    return project


def get_project(company, user, project_id: str):
    # PermissionChecker, _reachable_project_ids — imported at top of file.

    project = get_project_object(company, project_id)
    if not project:
        return None
    if PermissionChecker.can(user, "project.view", obj=project):
        return project
    # Fallback: a topic-scoped RoleAssignment doesn't show up in the direct
    # check above (project.view's own scope chain never looks at topics
    # below it), but it DOES make this project "reachable" -- same logic
    # visible_projects() already uses for its narrow-case listing. Without
    # this, a topic-only invitee can see the project in their sidebar but
    # 404s the moment they try to open it. See #120.
    if project.id in _reachable_project_ids(user):
        return project
    return None


def get_project_object(company, project_id: str):
    """
    Plain fetch, no permission filtering. Used when a caller needs the
    object itself before deciding which specific right to check against
    it (e.g. delete_project needs to check 'project.delete', not 'project.view',
    so it can't reuse get_project()'s built-in view-right check).
    """
    # Project — imported at top of file.
    return Project.objects.filter(company=company, id=project_id, is_active=True).first()


def archive_project(project):
    """Caller (workspace/api.py) has already fetched + permission-checked the object."""
    project.soft_delete()
    return project


def remove_user_from_server(company, user_id: str, requesting_user) -> dict:
    # CompanyAccess, ProjectMember — imported at top of file.

    if str(requesting_user.id) == user_id:
        raise ValueError("You cannot remove yourself from the server.")

    access = CompanyAccess.objects.filter(
        company=company, user_id=user_id, is_active=True
    ).select_related("user").first()
    if not access:
        raise ValueError("User is not a member of this server.")
    if access.role == CompanyAccess.Role.OWNER:
        raise ValueError("Cannot remove the server owner.")

    email = access.user.email or str(user_id)
    access.is_active = False
    access.save(update_fields=["is_active", "updated_at"])
    ProjectMember.objects.filter(
        company=company, user_id=user_id, is_active=True
    ).update(is_active=False)
    TopicParticipant.objects.filter(
        company=company, user_id=user_id, is_active=True
    ).update(is_active=False)
    # The rights themselves. Left in place, they outlive the membership and
    # come back with the next invite -- a removed company Admin re-invited
    # into one topic would still be a company Admin. The legacy Django group
    # carries the old has_perm() checks and goes the same way.
    revoke_all_roles(company, access.user)
    access.user.groups.clear()
    return {"ok": True, "message": f"{email} removed from server."}


def get_member(company, user_id: str):
    """The User behind an active membership, or None."""
    # CompanyAccess — imported at top of file.
    access = CompanyAccess.objects.filter(company=company, user_id=user_id, is_active=True).select_related("user").first()
    return access.user if access else None


def member_access(company, user) -> dict:
    """
    What `user` holds on this server, in the shape an invite sends: a
    server-wide role (a company-scope assignment), or the projects/topics
    they were scoped to. Read from RoleAssignment -- the rows the checker
    reads -- not from the legacy CompanyAccess flag, which cannot say which.
    """
    # RoleAssignment, Project, ChatTopic, CompanyAccess — imported at top of file.

    rows = list(RoleAssignment.objects.filter(user=user).select_related("role"))
    company_row = next((a for a in rows if a.scope_object_type == "company" and a.scope_object_id == company.id), None)
    project_rows = {a.scope_object_id: a for a in rows if a.scope_object_type == "project"}
    topic_rows = {a.scope_object_id: a for a in rows if a.scope_object_type == "topic"}

    grants = {}
    for p in Project.objects.filter(company=company, id__in=project_rows, is_active=True).order_by("name"):
        grants[p.id] = {"project_id": str(p.id), "topic_ids": []}
    for t in ChatTopic.objects.filter(company=company, id__in=topic_rows, is_active=True).order_by("created_at"):
        if t.project_id in project_rows:
            continue  # the whole project already covers it
        grants.setdefault(t.project_id, {"project_id": str(t.project_id), "topic_ids": []})["topic_ids"].append(str(t.id))

    names = {p.id: p.name for p in Project.objects.filter(company=company, id__in=list(grants))}
    first = company_row or next(iter(project_rows.values()), None) or next(iter(topic_rows.values()), None)
    access = CompanyAccess.objects.filter(company=company, user=user, is_active=True).first()
    role = first.role.name.lower() if first else (access.role if access else CompanyAccess.Role.MEMBER)
    return {
        "user_id": str(user.id), "role": role, "server_wide": company_row is not None,
        "grants": [grants[pid] for pid in sorted(grants, key=lambda pid: names.get(pid, "").lower())],
    }


def set_member_access(company, actor, target_user_id: str, role: str, grants: list) -> dict:
    """
    Replace what a member holds: everything they had goes, then either the
    server-wide role (no grants) or exactly these grants, at `role` -- the same
    rule an invite follows. The legacy CompanyAccess.role and Django group
    follow, so the members list and the old has_perm() checks agree.

    Refuses the owner (nothing on this server outranks them), the caller's own
    row (locking yourself out is not something the UI should offer), and
    handing out ownership. Validated before anything is written.
    """
    from django.contrib.auth.models import Group
    # CompanyAccess, ProjectMember, TopicParticipant, Role, PermissionChecker — imported at top of file.

    valid_roles = [r.value for r in CompanyAccess.Role]
    if role not in valid_roles:
        raise ValueError(f"Invalid role '{role}'. Must be one of: {', '.join(valid_roles)}")
    if role == CompanyAccess.Role.OWNER:
        raise ValueError("Ownership cannot be granted here.")
    if str(actor.id) == str(target_user_id):
        raise ValueError("You cannot change your own access.")
    access = CompanyAccess.objects.filter(company=company, user_id=target_user_id, is_active=True).select_related("user").first()
    if not access:
        raise ValueError("User is not a member of this server.")
    if access.role == CompanyAccess.Role.OWNER or str(company.owner_id) == str(target_user_id):
        raise ValueError("The owner's access cannot be changed.")
    role_row = Role.objects.filter(company=company, name=role.capitalize()).first()
    if role_row is None:
        raise ValueError(f"Role '{role}' is not set up on this server. Run manage.py seed_permissions.")
    resolved = _resolve_grants(company, grants)
    user = access.user

    revoke_all_roles(company, user)
    access.role = role
    access.save(update_fields=["role", "updated_at"])
    if resolved:
        # Scoped: the legacy roster rows are re-derived from the grants, and the
        # company-wide group goes with the company-wide role.
        ProjectMember.objects.filter(company=company, user=user, is_active=True).update(is_active=False)
        TopicParticipant.objects.filter(company=company, user=user, is_active=True).update(is_active=False)
        user.groups.clear()
        apply_grants(company, user, [_grant_dict(p, t) for p, t in resolved], role, actor)
    else:
        PermissionChecker.assign_role(user, role_row, company, granted_by=actor)
        group = Group.objects.filter(name=role.capitalize()).first()
        user.groups.set([group] if group else [])
    logger.info("[access] %s set %s to %s (%s)", actor.email, user.email, role, "scoped" if resolved else "server-wide")
    return member_access(company, user)


def revoke_all_roles(company, user) -> int:
    """Delete every RoleAssignment `user` holds in `company`, at any scope."""
    # RoleAssignment, Project, ChatTopic, Q — imported at top of file.

    project_ids = Project.objects.filter(company=company).values_list("id", flat=True)
    topic_ids = ChatTopic.objects.filter(company=company).values_list("id", flat=True)
    deleted, _ = RoleAssignment.objects.filter(user=user).filter(
        Q(scope_object_type="company", scope_object_id=company.id)
        | Q(scope_object_type="project", scope_object_id__in=project_ids)
        | Q(scope_object_type="topic", scope_object_id__in=topic_ids)
    ).delete()
    return deleted


# ── Channels ──────────────────────────────────────────────────────────────────

def list_channels(user, project, include_archived=False):
    # visible_channels — imported at top of file.
    return visible_channels(user, project, include_archived=include_archived)


def create_channel(company, project, name: str, description: str = None):
    # Channel — imported at top of file.

    slug = _unique_channel_slug(project, name)
    return Channel.objects.create(
        company=company, project=project, name=name,
        slug=slug, description=description or "",
    )


def get_channel(company, project, channel_id: str):
    # Channel — imported at top of file.
    return Channel.objects.filter(
        company=company, project=project, id=channel_id, is_active=True
    ).first()


def archive_channel(channel):
    """Caller (workspace/api.py) has already fetched + permission-checked the object."""
    channel.soft_delete()
    return channel


# ── Topics ────────────────────────────────────────────────────────────────────

def list_topics(user, channel, include_archived=False):
    # visible_topics — imported at top of file.
    return visible_topics(user, channel, include_archived=include_archived)


def create_topic(company, project, channel, title: str, creator=None):
    # ChatTopic — imported at top of file.

    slug = _unique_topic_slug(channel, title)
    return ChatTopic.objects.create(
        company=company, project=project, channel=channel, title=title, slug=slug,
    )


def update_topic(project, channel, topic, title: str):
    """Caller (workspace/api.py) has already fetched + permission-checked `topic`."""
    topic.title = title
    topic.slug = _unique_topic_slug(channel, title)
    topic.save(update_fields=["title", "slug", "updated_at"])
    return topic


def get_topic(company, project, channel, topic_id: str):
    # ChatTopic — imported at top of file.
    return ChatTopic.objects.filter(
        company=company, project=project, channel=channel,
        id=topic_id, is_active=True
    ).first()


def archive_topic(topic):
    """Caller (workspace/api.py) has already fetched + permission-checked the object."""
    topic.soft_delete()
    return topic


def mark_topic_read(user, topic) -> None:
    # ChatReadMarker, ChatMessage — imported at top of file.

    latest = (
        ChatMessage.objects.filter(topic=topic, is_active=True)
        .order_by("-created_at").first()
    )
    if latest is None:
        return
    ChatReadMarker.objects.update_or_create(
        user=user, topic=topic, defaults={"last_read_message": latest},
    )


def get_topic_unread_map(user, topics) -> dict:
    # ChatReadMarker, ChatMessage — imported at top of file.

    topic_ids = [t.id for t in topics]
    markers = {
        m.topic_id: m.last_read_message
        for m in ChatReadMarker.objects.filter(
            user=user, topic_id__in=topic_ids
        ).select_related("last_read_message")
    }
    result = {}
    for topic in topics:
        marker_msg = markers.get(topic.id)
        if marker_msg is None:
            result[str(topic.id)] = ChatMessage.objects.filter(
                topic=topic, is_active=True
            ).count()
        else:
            result[str(topic.id)] = ChatMessage.objects.filter(
                topic=topic, is_active=True, created_at__gt=marker_msg.created_at,
            ).count()
    return result


# ── Members ───────────────────────────────────────────────────────────────────

def get_member_access(company, user):
    # CompanyAccess — imported at top of file.
    return CompanyAccess.objects.filter(
        company=company, user=user, is_active=True,
    ).first()


def _send_invite_email(company, email: str, redirect_to: str | None) -> tuple[bool, str | None]:
    """
    Email the invitee through Supabase's admin invite API when this server
    holds the service key. Returns (email_sent, note) -- the note says why
    nothing was sent so the inviter can pass the steps on. The invite seeds
    the new account with this server (nx_servers), which the web app shows
    on the invitee's launcher.
    """
    from authn.supabase import SupabaseAdminError, invite_user_by_email, send_recovery_email

    if not settings.SUPABASE_SERVICE_KEY:
        # A configuration gap, not a delivery failure -- say which, so the
        # admin reading the toast knows what to set rather than wondering
        # whether the address was wrong.
        return False, "This server is not set up to send email -- no SUPABASE_SERVICE_KEY is configured."
    if redirect_to and not redirect_to.startswith(("http://", "https://")):
        redirect_to = None
    server_url = (getattr(settings, "NEURALOPS_SERVER_URL", "") or "").rstrip("/")
    metadata = None
    if server_url:
        metadata = {"nx_servers": [{
            "id": secrets.token_urlsafe(8), "name": company.name, "url": server_url,
            "addedAt": timezone.now().isoformat(),
        }]}
    try:
        invite_user_by_email(email, redirect_to=redirect_to or "", metadata=metadata)
        return True, None
    except SupabaseAdminError as exc:
        logger.warning("[invite] email to %s not sent: %s", email, exc)
        if exc.code == "exists":
            # Supabase says "registered" for any address it knows -- one merely
            # invited before and never claimed, or a member removed here. The
            # account exists either way, so a sign-in (password reset) email is
            # what gets them in; it lands on the same page the invite would.
            try:
                send_recovery_email(email, redirect_to=redirect_to or "")
                return True, "They already had a NeuralOps account, so a sign-in email was sent instead."
            except SupabaseAdminError as exc2:
                logger.warning("[invite] recovery email to %s not sent: %s", email, exc2)
                return False, "They already have a NeuralOps account, but no email could be sent -- they can sign in and add this server."
        return False, "The invitation email could not be sent; pass the steps on instead."


def invite_to_system(company, inviter, email: str, role: str = "member", grants: list | None = None,
                     redirect_to: str | None = None) -> dict:
    """
    The ONE entry point for adding anyone to this company. Every other
    invite (invite_to_project() below, and by extension its topic-scope
    case) calls this FIRST to guarantee real system-level membership,
    then layers its narrower grants on top. Idempotent -- calling it on
    someone who's already a member adds nothing but the grants.

    Was named send_invite() -- same job (it's still what POST
    /members/invite/ calls), renamed + fixed as part of #120: the old
    version only ever created a CompanyAccess row (the legacy "is this
    person a member" flag) and never the RoleAssignment row that
    PermissionChecker actually checks, so invited people had no real
    rights at all.

    `grants` -- [{"project_id", "topic_ids"}] -- are the projects/topics
    they also get `role` in (see apply_grants). Refused up front if any id
    is unknown, so nothing is half-applied. Two outcomes:
      - Known platform user (already a member, or not on this company yet)
        -> CompanyAccess + a company-scope RoleAssignment if missing, then
        the grants, immediately. An existing member keeps their server
        role; only the grants use `role`.
      - Nobody with this email exists yet -> create a pending Invitation
        (token + link) carrying the grants, and stop. Membership + every
        RoleAssignment happen later, when they accept -- see auth_verify()
        / _add_user_to_invited_project() in authn/services.py.
    """
    # CompanyAccess, Invitation, Role, PermissionChecker, User — imported at top of file.

    valid_roles = [r.value for r in CompanyAccess.Role]
    if role not in valid_roles:
        raise ValueError(f"Invalid role '{role}'. Must be one of: {', '.join(valid_roles)}")
    grants = [_grant_dict(project, topics) for project, topics in _resolve_grants(company, grants)]

    existing_access = CompanyAccess.objects.filter(
        company=company, user__email=email, is_active=True
    ).select_related("user").first()
    if existing_access:
        applied = apply_grants(company, existing_access.user, grants, role, inviter)
        added = f" — now also in {_describe_grants(applied)}" if applied else ""
        return {
            "ok": True, "is_new_user": False, "email": email, "role": existing_access.role,
            "message": f"{email} is already a member of this server{added}.",
            "grants": applied,
        }

    user = User.objects.filter(email=email, is_active=True).first()
    if user:
        # A removed member leaves a deactivated row behind (one per company
        # and user) -- bring it back rather than tripping the constraint.
        CompanyAccess.objects.update_or_create(
            company=company, user=user,
            defaults={"role": role, "invited_by": inviter, "is_active": True},
        )
        if grants:
            # Scoped on purpose: the role lands on the named projects/topics
            # only. A company-scope role reaches every project (project.list,
            # channel.list, topic.list are in every default bundle) and would
            # undo the scoping -- see row_rules.visible_*.
            applied = apply_grants(company, user, grants, role, inviter)
        else:
            company_role = Role.objects.filter(company=company, name=role.capitalize()).first()
            if company_role:
                PermissionChecker.assign_role(user, company_role, company, granted_by=inviter)
            applied = []
        added = f" and to {_describe_grants(applied)}" if applied else ""
        return {
            "ok": True, "is_new_user": False, "email": email, "role": role,
            "message": f"{email} added to this server{added}.",
            "grants": applied,
        }

    if Invitation.objects.filter(
        company=company, email=email, status=Invitation.Status.PENDING, is_active=True,
    ).exists():
        raise ValueError(f"An active invitation has already been sent to {email}.")

    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    invitation = Invitation.objects.create(
        company=company, email=email, role=role, invited_by=inviter,
        token_hash=token_hash, expires_at=timezone.now() + timedelta(days=7),
        access_payload={"grants": grants} if grants else {},
    )
    email_sent, email_note = _send_invite_email(company, email, redirect_to)
    return {
        "ok": True, "is_new_user": True,
        "message": f"Invitation email sent to {email}" if email_sent else f"{email} is pre-authorised on this server",
        "email": email, "role": role,
        "expires_at": invitation.expires_at.isoformat(),
        "email_sent": email_sent, "email_note": email_note,
        "grants": grants,
    }


def list_members(company) -> list:
    # CompanyAccess — imported at top of file.

    members = CompanyAccess.objects.filter(
        company=company, is_active=True,
    ).select_related("user", "invited_by")
    return [
        {
            "user_id": str(m.user.id),
            "email": m.user.email,
            "role": m.role,
            "invited_by": m.invited_by.email if m.invited_by else None,
            "joined_at": m.joined_at.isoformat(),
            "avatar": m.user.get_avatar_url(),  # #148
        }
        for m in members
    ]


def remove_member(company, caller, target_user_id: str) -> dict:
    # CompanyAccess — imported at top of file.

    try:
        target_access = CompanyAccess.objects.get(
            company=company, user__id=target_user_id, is_active=True,
        )
    except CompanyAccess.DoesNotExist:
        raise ValueError("Member not found.")

    if target_access.role == CompanyAccess.Role.OWNER:
        raise ValueError("Cannot remove the server owner.")
    if target_access.user == caller:
        raise ValueError("You cannot remove yourself.")

    target_access.soft_delete()
    return {"ok": True, "message": f"{target_access.user.email} has been removed from this server."}


# ── Team ──────────────────────────────────────────────────────────────────────

def _format_member(member) -> dict:
    user = member.user
    # Avatar lives on User itself (shared by humans + personas -- see #148),
    # not on the Persona profile model -- that still has its own (largely
    # unpopulated) avatar field, but User.avatar is the one actually kept up
    # to date by assign_avatar().
    avatar = user.get_avatar_url()
    if user.user_type == "persona":
        profile = getattr(user, "persona_profile", None)
        if profile and profile.is_active:
            name = profile.name
        else:
            name = user.username  # fallback: shouldn't normally happen
        email = ""
    else:
        # User.get_display_name() (display_name, else the email local-part) is
        # now the ONLY name source for humans. The old `human_profile` lookup
        # is gone with the Human model -- the table was never populated for
        # device-auth users anyway (DECISIONS.md §3), so this branch was
        # always the one that actually ran.
        name = user.get_display_name()
        email = user.email or ""
    return {
        "id": str(member.id), "user_id": str(user.id),
        "name": name, "email": email, "role": member.role,
        "member_type": user.user_type, "avatar": avatar,
    }


def list_team(company, project) -> list:
    # ProjectMember — imported at top of file.

    members = (
        ProjectMember.objects.filter(company=company, project=project, is_active=True)
        .filter(user__is_active=True)  # exclude deactivated persona shadow users
        .select_related("user", "user__persona_profile")
        .order_by("role", "created_at")
    )
    return [_format_member(m) for m in members]


def add_member(company, project, user_id: str, role: str = "member") -> dict:
    # ProjectMember — imported at top of file.

    user = User.objects.filter(id=user_id, is_active=True).first()
    if not user:
        raise ValueError("User not found.")

    member = ProjectMember.objects.filter(
        company=company, project=project, user=user
    ).first()
    if member:
        if member.is_active:
            raise ValueError("This person is already a member of this project.")
        member.is_active = True
        member.role = role
        member.save(update_fields=["is_active", "role"])
    else:
        member = ProjectMember.objects.create(
            company=company, project=project, user=user, role=role,
        )
    return _format_member(member)


def remove_team_member(company, project, user_id: str, requesting_user) -> dict:
    # ProjectMember — imported at top of file.

    member = ProjectMember.objects.filter(
        company=company, project=project, user_id=user_id, is_active=True
    ).first()
    if not member:
        raise ValueError("Member not found.")
    if member.role == ProjectMember.Role.OWNER:
        raise ValueError("Cannot remove the project owner.")
    if str(member.user_id) == str(requesting_user.id):
        raise ValueError("You cannot remove yourself from the project.")

    member.soft_delete()
    return {"ok": True, "message": f"{member.user.email or 'Member'} removed from project."}


def invite_to_project(
    company, inviter, project,
    email: str = None, persona_name: str = None,
    scope: str = "topic", topic_id: str = None, role: str = "member",
    redirect_to: str | None = None,
) -> dict:
    # CompanyAccess, Invitation, ProjectMember, Persona — imported at top of file.

    # ── Persona invite ────────────────────────────────────────────────────────
    if persona_name:
        name = persona_name.lstrip("@").strip()
        # Scoped to THIS project, not the whole company. Looking up by company
        # let you add a persona owned by project A to project B's member list:
        # the sidebar showed them on the team, but get_persona_by_mention()
        # filters by project, returned None, and the @mention silently did
        # nothing. Persona.project is the single source of ownership.
        persona = Persona.objects.filter(
            company=company, project=project, name__iexact=name, is_active=True
        ).select_related("identity_user").first()
        if not persona:
            raise ValueError(f"Persona '@{name}' not found in this project.")
        member = ProjectMember.objects.filter(
            company=company, project=project, user=persona.identity_user
        ).first()
        if member and member.is_active:
            raise ValueError(f"@{persona.name} is already in this project.")
        if member:
            member.is_active = True
            member.role = role
            member.save(update_fields=["is_active", "role"])
        else:
            ProjectMember.objects.create(
                company=company, project=project,
                user=persona.identity_user, role=role,
            )
        return {
            "ok": True, "is_new_user": False,
            "email": "", "scope": scope,
            "message": f"@{persona.name} added to this project.",
        }

    if not email:
        raise ValueError("Provide either an email address or a persona name.")

    # One grant -- the whole project, or just this topic. invite_to_system()
    # owns membership and applies it at once for a known user, or stores it
    # on the pending Invitation for acceptance when they are brand new. Both
    # end in apply_grants(), so a /invite and a members-page invite write the
    # same rows. See #120.
    grant = {"project_id": str(project.id), "topic_ids": [topic_id] if scope == "topic" and topic_id else []}
    system_result = invite_to_system(company, inviter, email, role=role, grants=[grant], redirect_to=redirect_to)

    if system_result["is_new_user"]:
        return {**system_result, "scope": scope}
    return {"ok": True, "is_new_user": False, "email": email, "scope": scope, "message": f"{email} added."}


def _add_to_topic(company, project, topic_id: str, user, role: str = "participant"):
    # ChatTopic, TopicParticipant — imported at top of file.

    topic = ChatTopic.objects.filter(
        company=company, project=project, id=topic_id, is_active=True
    ).first()
    if not topic:
        return
    participant, _ = TopicParticipant.objects.get_or_create(
        company=company, project=project, topic=topic, user=user,
        defaults={"role": TopicParticipant.Role.PARTICIPANT},
    )
    # Removal deactivates participations; an invite back must revive them.
    if not participant.is_active:
        participant.is_active = True
        participant.save(update_fields=["is_active"])


def apply_grants(company, user, grants: list, role: str, granted_by, strict: bool = True) -> list:
    """
    Give `user` the `role` in each project or topic listed -- the one place
    that writes both the legacy rows (ProjectMember / TopicParticipant) and
    the RoleAssignment the checker actually reads. Every invite path ends
    here: an existing member at once, a brand-new one at acceptance, the
    composer's /invite with its single grant.

    A grant is {"project_id", "topic_ids"}. No topic_ids = the whole project:
    one project-scope assignment, which reaches topics created later too.
    With ids = only those topics, each its own topic-scope assignment, so
    they cannot see siblings. Idempotent -- re-applying creates nothing.

    strict: refuse an unknown or archived id (ValueError) before writing
    anything. Off at acceptance, where a project archived since the invite
    was sent is skipped rather than failing the sign-in.

    Returns the grants actually applied, in the request's shape.
    """
    # ProjectMember, Role, PermissionChecker — imported at top of file.

    resolved = _resolve_grants(company, grants, strict=strict)
    project_role = Role.objects.filter(company=company, name=role.capitalize()).first()
    if resolved and project_role is None:
        # Membership rows without the RoleAssignment would look granted and
        # confer nothing -- refuse rather than half-apply.
        if strict:
            raise ValueError(f"Role '{role}' is not set up on this server. Run manage.py seed_permissions.")
        logger.warning("[invite] role %r is not seeded; %s gets membership rows but no rights", role, user.email)
    applied = []
    for project, topics in resolved:
        member = ProjectMember.objects.filter(company=company, project=project, user=user).first()
        if not member:
            ProjectMember.objects.create(company=company, project=project, user=user, role=role)
        elif not member.is_active:
            member.is_active = True
            member.role = role
            member.save(update_fields=["is_active", "role"])

        if topics:
            for topic in topics:
                _add_to_topic(company, project, str(topic.id), user, role)
                if project_role:
                    PermissionChecker.assign_role(user, project_role, topic, granted_by=granted_by)
        elif project_role:
            PermissionChecker.assign_role(user, project_role, project, granted_by=granted_by)

        applied.append(_grant_dict(project, topics))
        logger.info(
            "[invite] user=%s granted %s in project=%s",
            user.email, f"{len(topics)} topic(s)" if topics else "the whole project", project.name,
        )
    return applied


def _resolve_grants(company, grants, strict: bool = True) -> list:
    """
    Turn grant dicts into (project, topics) pairs. Entries for the same
    project merge, and a whole-project entry wins over topic lists for it.
    Unknown, archived or malformed ids raise ValueError when strict and are
    dropped otherwise; a topic list whose topics are all gone drops the
    project rather than widening it to the whole project.
    """
    # Project, ChatTopic — imported at top of file.

    merged = {}  # project id -> set of topic ids, or None for the whole project
    for grant in grants or []:
        project_id = _as_uuid(grant.get("project_id"))
        if not project_id:
            if strict:
                raise ValueError("A grant is missing its project.")
            continue
        raw_topic_ids = grant.get("topic_ids") or []
        topic_ids = {t for t in (_as_uuid(x) for x in raw_topic_ids) if t}
        if len(topic_ids) < len(set(raw_topic_ids)) and strict:
            raise ValueError("A topic id is malformed.")
        if merged.get(project_id, ()) is None:
            continue
        if not topic_ids:
            merged[project_id] = None
        else:
            merged.setdefault(project_id, set()).update(topic_ids)

    resolved = []
    for project_id, topic_ids in merged.items():
        project = Project.objects.filter(company=company, id=project_id, is_active=True).first()
        if not project:
            if strict:
                raise ValueError(f"Project {project_id} was not found.")
            continue
        topics = []
        if topic_ids:
            topics = list(ChatTopic.objects.filter(
                company=company, project=project, id__in=topic_ids, is_active=True,
            ))
            missing = topic_ids - {t.id for t in topics}
            if missing and strict:
                raise ValueError(f"Topic {min(str(m) for m in missing)} was not found in project '{project.name}'.")
            if not topics:
                continue
        resolved.append((project, topics))
    return resolved


def _as_uuid(value):
    try:
        return uuid.UUID(str(value)) if value else None
    except ValueError:
        return None


def _grant_dict(project, topics) -> dict:
    return {"project_id": str(project.id), "topic_ids": [str(t.id) for t in topics]}


def _describe_grants(grants: list) -> str:
    """'2 projects and 3 topics' -- for the outcome message."""
    projects = sum(1 for g in grants if not g["topic_ids"])
    topics = sum(len(g["topic_ids"]) for g in grants)
    parts = [f"{n} {word}{'' if n == 1 else 's'}" for n, word in ((projects, "project"), (topics, "topic")) if n]
    return " and ".join(parts)


def list_available_users(company, project, search: str = "") -> list:
    # CompanyAccess, ProjectMember, Q — imported at top of file.

    in_project = ProjectMember.objects.filter(
        company=company, project=project, is_active=True
    ).values_list("user_id", flat=True)
    workspace_ids = CompanyAccess.objects.filter(
        company=company, is_active=True
    ).values_list("user_id", flat=True)
    qs = User.objects.filter(
        id__in=workspace_ids, user_type="human", is_active=True,
    ).exclude(id__in=in_project)

    # Searched against User's own columns now -- the Human profile table it
    # used to search (human_profile__full_name / __email) is gone, and it was
    # never populated for device-auth users in the first place.
    if search:
        qs = qs.filter(
            Q(display_name__icontains=search) | Q(email__icontains=search)
        )
    return [
        {
            "user_id": str(user.id),
            "name": user.get_display_name(),
            "email": user.email or "",
            "avatar": user.get_avatar_url(),  # #148 -- lives on User
        }
        for user in qs
    ]


def list_available_personas(company, project) -> list:
    # Persona, ProjectMember — imported at top of file.

    in_project = ProjectMember.objects.filter(
        company=company, project=project, is_active=True, user__user_type="persona",
    ).values_list("user_id", flat=True)
    # Scoped to THIS project, matching invite_to_project()'s own lookup --
    # personas are project-owned and not transferable, so offering another
    # project's persona here would just produce a "not found in this project"
    # error on the invite that follows.
    personas = Persona.objects.filter(
        company=company, project=project, is_active=True
    ).exclude(identity_user_id__in=in_project).select_related("identity_user")
    return [
        {
            "persona_id": str(p.id), "user_id": str(p.identity_user_id),
            "name": p.name,
            "avatar": p.identity_user.get_avatar_url(),  # #148 -- lives on User, not Persona
        }
        for p in personas
    ]


# ── Slug helpers ──────────────────────────────────────────────────────────────

def _unique_project_slug(company, name: str) -> str:
    # Project — imported at top of file.
    base = slugify(name) or "project"
    slug, n = base, 1
    while Project.objects.filter(company=company, slug=slug).exists():
        slug = f"{base}-{n}"
        n += 1
    return slug


def _unique_channel_slug(project, name: str) -> str:
    # Channel — imported at top of file.
    base = slugify(name) or "channel"
    slug, n = base, 1
    while Channel.objects.filter(project=project, slug=slug).exists():
        slug = f"{base}-{n}"
        n += 1
    return slug


def _unique_topic_slug(channel, title: str) -> str:
    # ChatTopic — imported at top of file.
    base = slugify(title) or "topic"
    slug, n = base, 1
    while ChatTopic.objects.filter(channel=channel, slug=slug).exists():
        slug = f"{base}-{n}"
        n += 1
    return slug
