"""
Business logic for Workspace (Projects, Channels, Topics), Members, and Team.
All queries are scoped to company — safe for multi-tenant use.
"""
import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils import timezone
from django.utils.text import slugify

from authn.permissions.checker import PermissionChecker
from authn.permissions.models import Role
from authn.permissions.row_rules import (
    _reachable_project_ids, visible_channels, visible_projects, visible_topics,
)
from nucleus.models import (
    ChatMessage, ChatReadMarker, ChatTopic, Channel, Company, CompanyAccess,
    Invitation, Persona, Project, ProjectMember, TopicParticipant,
)
import os
from nucleus.models import MCPServer
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

def provision_project_folder_and_mcp(project):


    folder_name = get_project_folder_name(project)
    folder_path = os.path.join(settings.PROJECTS_ROOT, folder_name)
    os.makedirs(folder_path, exist_ok=True)

    # project is a real FK now, not an M2M that application code kept to a
    # single entry -- so ownership is set at creation and there is no
    # follow-up .add() to forget.
    server = MCPServer.objects.create(
        company=project.company,
        project=project,
        name=f"{project.name} Files",
        server_type=MCPServer.ServerType.LOCAL,
        transport=MCPServer.Transport.STDIO,
        command=f"npx -y @modelcontextprotocol/server-filesystem {folder_path}",
        is_protected=True,
        is_default=True,
        config={"root_path": folder_path},
    )
    return server

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
    return {"ok": True, "message": f"{email} removed from server."}


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


def invite_to_system(company, inviter, email: str, role: str = "member", access_payload: dict = None) -> dict:
    """
    The ONE entry point for adding anyone to this company. Every other
    invite (invite_to_project() below, and by extension its topic-scope
    case) calls this FIRST to guarantee real system-level membership,
    then layers its own narrower grant on top. Idempotent -- calling it
    on someone who's already a member is a no-op.

    Was named send_invite() -- same job (it's still what POST
    /members/invite/ calls), renamed + fixed as part of #120: the old
    version only ever created a CompanyAccess row (the legacy "is this
    person a member" flag) and never the RoleAssignment row that
    PermissionChecker actually checks, so invited people had no real
    rights at all.

    Two outcomes:
      - Known platform user, just not on this company yet -> grant
        CompanyAccess + a company-scope RoleAssignment immediately.
      - Nobody with this email exists yet -> create a pending Invitation
        (token + link) and stop. Membership + the RoleAssignment happen
        later, when they accept -- see auth_verify() /
        _add_user_to_invited_project() in authn/services.py, which reads
        `access_payload` back out to finish the job.
    """
    # CompanyAccess, Invitation, Role, PermissionChecker, User — imported at top of file.

    valid_roles = [r.value for r in CompanyAccess.Role]
    if role not in valid_roles:
        raise ValueError(f"Invalid role '{role}'. Must be one of: {', '.join(valid_roles)}")

    existing_access = CompanyAccess.objects.filter(
        company=company, user__email=email, is_active=True
    ).first()
    if existing_access:
        return {
            "ok": True, "is_new_user": False, "email": email, "role": existing_access.role,
            "message": f"{email} is already a member of this server.",
        }

    user = User.objects.filter(email=email, is_active=True).first()
    if user:
        CompanyAccess.objects.create(company=company, user=user, role=role, invited_by=inviter)
        company_role = Role.objects.filter(company=company, name=role.capitalize()).first()
        if company_role:
            PermissionChecker.assign_role(user, company_role, company, granted_by=inviter)
        return {
            "ok": True, "is_new_user": False, "email": email, "role": role,
            "message": f"{email} added to this server.",
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
        access_payload=access_payload or {},
    )
    return {
        "ok": True, "is_new_user": True, "message": f"Invitation sent to {email}",
        "email": email, "role": role,
        "expires_at": invitation.expires_at.isoformat(),
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
    # not on the Human/Persona profile models -- those still have their own
    # (largely unpopulated) avatar fields, but User.avatar is now the one
    # actually kept up to date by assign_avatar().
    avatar = user.get_avatar_url()
    if user.user_type == "persona":
        profile = getattr(user, "persona_profile", None)
        if profile and profile.is_active:
            name = profile.name
        else:
            name = user.username  # fallback: shouldn't normally happen
        email = ""
    else:
        # Human profile may not exist (device-auth users have no Human record).
        # Fall back to User.get_display_name() which uses display_name or email local-part.
        name = user.get_display_name()
        email = user.email or ""
        try:
            hp = user.human_profile
            if hp.full_name:
                name = hp.full_name
            email = hp.email or email
        except Exception:
            pass
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
        .select_related("user", "user__human_profile", "user__persona_profile")
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

    # Step 1: invite_to_system() is the ONE place company membership gets
    # granted. Idempotent -- if this person is already a member, it's a
    # no-op and we fall straight through to the project-level grant below.
    # If they're brand new, it stashes {project_id, scope, topic_id} on the
    # pending Invitation so the project/topic grant can finish later, at
    # acceptance (see authn/services.py: auth_verify /
    # _add_user_to_invited_project). See #120.
    system_result = invite_to_system(
        company, inviter, email, role=role,
        access_payload={"project_id": str(project.id), "scope": scope, "topic_id": topic_id},
    )

    if system_result["is_new_user"]:
        return {**system_result, "scope": scope}

    # Step 2: real system member now (just granted above, or already was)
    # -- add the legacy project membership row.
    user = User.objects.filter(email=email, is_active=True).first()

    member = ProjectMember.objects.filter(
        company=company, project=project, user=user
    ).first()
    if not member:
        ProjectMember.objects.create(
            company=company, project=project, user=user, role=role
        )
    elif not member.is_active:
        member.is_active = True
        member.role = role
        member.save(update_fields=["is_active", "role"])

    # Step 3: the actual RBAC grant -- scoped to the project OR the one
    # topic, never both, so a topic-only invite stays narrow (can't see
    # sibling topics -- that's the whole point of scope="topic").
    project_role = Role.objects.filter(company=company, name=role.capitalize()).first()
    if scope == "topic" and topic_id:
        _add_to_topic(company, project, topic_id, user, role)
        topic = ChatTopic.objects.filter(
            company=company, project=project, id=topic_id, is_active=True
        ).first()
        if topic and project_role:
            PermissionChecker.assign_role(user, project_role, topic, granted_by=inviter)
    elif project_role:
        PermissionChecker.assign_role(user, project_role, project, granted_by=inviter)

    return {"ok": True, "is_new_user": False, "email": email, "scope": scope, "message": f"{email} added."}


def _add_to_topic(company, project, topic_id: str, user, role: str = "participant"):
    # ChatTopic, TopicParticipant — imported at top of file.

    topic = ChatTopic.objects.filter(
        company=company, project=project, id=topic_id, is_active=True
    ).first()
    if not topic:
        return
    TopicParticipant.objects.get_or_create(
        company=company, project=project, topic=topic, user=user,
        defaults={"role": TopicParticipant.Role.PARTICIPANT},
    )


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
    ).exclude(id__in=in_project).select_related("human_profile")

    if search:
        qs = qs.filter(
            Q(human_profile__full_name__icontains=search)
            | Q(human_profile__email__icontains=search)
        )
    result = []
    for user in qs:
        profile = getattr(user, "human_profile", None)
        result.append({
            "user_id": str(user.id),
            "name": profile.full_name if profile else user.email,
            "email": profile.email if profile else user.email,
            "avatar": user.get_avatar_url(),  # #148 -- lives on User, not Human
        })
    return result


def list_available_personas(company, project) -> list:
    # Persona, ProjectMember — imported at top of file.

    in_project = ProjectMember.objects.filter(
        company=company, project=project, is_active=True, user__user_type="persona",
    ).values_list("user_id", flat=True)
    personas = Persona.objects.filter(
        company=company, is_active=True
    ).exclude(identity_user_id__in=in_project).select_related("identity_user")
    return [
        {
            "persona_id": str(p.id), "user_id": str(p.identity_user_id),
            "name": p.name, "source_type": p.source_type,
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
