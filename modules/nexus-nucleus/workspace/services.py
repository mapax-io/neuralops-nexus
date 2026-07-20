"""
Business logic for Workspace (Projects, Channels, Topics), Members, and Team.
All queries are scoped to company — safe for multi-tenant use.
"""
import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.utils.text import slugify

User = get_user_model()


def get_company():
    from nucleus.models import Company
    return Company.objects.filter(is_active=True).first()


# ── Projects ──────────────────────────────────────────────────────────────────

def list_projects(company, user):
    from nucleus.models import Project, CompanyAccess

    access = CompanyAccess.objects.filter(
        company=company, user=user, is_active=True
    ).first()

    if access and access.role in ("owner", "admin"):
        return Project.objects.filter(company=company, is_active=True).order_by("name")

    return Project.objects.filter(
        company=company,
        is_active=True,
        projectmember_items__user=user,
        projectmember_items__is_active=True,
    ).distinct().order_by("name")


def create_project(company, user, name: str, description: str = None):
    from nucleus.models import Project, Channel, ProjectMember

    slug = _unique_project_slug(company, name)

    project = Project.objects.create(
        company=company, name=name, slug=slug, description=description or "",
    )
    Channel.objects.create(
        company=company, project=project, name="general",
        slug="general", description="General discussion",
    )
    ProjectMember.objects.create(
        company=company, project=project, user=user, role=ProjectMember.Role.ADMIN,
    )
    return project


def get_project(company, user, project_id: str):
    from nucleus.models import Project, CompanyAccess

    project = Project.objects.filter(
        company=company, id=project_id, is_active=True
    ).first()
    if not project:
        return None

    access = CompanyAccess.objects.filter(
        company=company, user=user, is_active=True
    ).first()
    if access and access.role in ("owner", "admin"):
        return project
    if project.projectmember_items.filter(user=user, is_active=True).exists():
        return project
    return None


def delete_project(company, project_id: str):
    from nucleus.models import Project

    project = Project.objects.filter(
        company=company, id=project_id, is_active=True
    ).first()
    if project:
        project.soft_delete()
    return project


def remove_user_from_server(company, user_id: str, requesting_user) -> dict:
    from nucleus.models import CompanyAccess, ProjectMember

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

def list_channels(company, project):
    return project.channel_items.filter(company=company, is_active=True).order_by("name")


def create_channel(company, project, name: str, description: str = None):
    from nucleus.models import Channel

    slug = _unique_channel_slug(project, name)
    return Channel.objects.create(
        company=company, project=project, name=name,
        slug=slug, description=description or "",
    )


def get_channel(company, project, channel_id: str):
    from nucleus.models import Channel
    return Channel.objects.filter(
        company=company, project=project, id=channel_id, is_active=True
    ).first()


# ── Topics ────────────────────────────────────────────────────────────────────

def list_topics(company, project, channel):
    return channel.topics.filter(
        company=company, project=project, is_active=True
    ).order_by("created_at")


def create_topic(company, project, channel, title: str, creator=None):
    from nucleus.models import ChatTopic

    slug = _unique_topic_slug(channel, title)
    return ChatTopic.objects.create(
        company=company, project=project, channel=channel, title=title, slug=slug,
    )


def get_topic(company, project, channel, topic_id: str):
    from nucleus.models import ChatTopic
    return ChatTopic.objects.filter(
        company=company, project=project, channel=channel,
        id=topic_id, is_active=True
    ).first()


def mark_topic_read(user, topic) -> None:
    from nucleus.models import ChatReadMarker, ChatMessage

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
    from nucleus.models import ChatReadMarker, ChatMessage

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
            ).exists()
        else:
            result[str(topic.id)] = ChatMessage.objects.filter(
                topic=topic, is_active=True, created_at__gt=marker_msg.created_at,
            ).exists()
    return result


# ── Members ───────────────────────────────────────────────────────────────────

def get_member_access(company, user):
    from nucleus.models import CompanyAccess
    return CompanyAccess.objects.filter(
        company=company, user=user, is_active=True,
    ).first()


def send_invite(company, inviter, email: str, role: str) -> dict:
    from nucleus.models import CompanyAccess, Invitation

    valid_roles = [r.value for r in CompanyAccess.Role]
    if role not in valid_roles:
        raise ValueError(f"Invalid role '{role}'. Must be one of: {', '.join(valid_roles)}")

    if CompanyAccess.objects.filter(company=company, user__email=email, is_active=True).exists():
        raise ValueError(f"{email} is already a member of this server.")

    if Invitation.objects.filter(
        company=company, email=email, status=Invitation.Status.PENDING, is_active=True,
    ).exists():
        raise ValueError(f"An active invitation has already been sent to {email}.")

    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    invitation = Invitation.objects.create(
        company=company, email=email, role=role, invited_by=inviter,
        token_hash=token_hash, expires_at=timezone.now() + timedelta(days=7),
    )
    return {
        "ok": True, "message": f"Invitation sent to {email}",
        "email": email, "role": role,
        "expires_at": invitation.expires_at.isoformat(),
    }


def list_members(company) -> list:
    from nucleus.models import CompanyAccess

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
        }
        for m in members
    ]


def remove_member(company, caller, target_user_id: str) -> dict:
    from nucleus.models import CompanyAccess

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
    if user.user_type == "persona":
        profile = getattr(user, "persona_profile", None)
        name = profile.name if profile else user.username
        avatar = profile.avatar.url if (profile and profile.avatar) else None
        email = ""
    else:
        profile = getattr(user, "human_profile", None)
        name = profile.full_name if profile else user.email
        email = profile.email if profile else user.email
        avatar = profile.avatar.url if (profile and profile.avatar) else None
    return {
        "id": str(member.id), "user_id": str(user.id),
        "name": name, "email": email, "role": member.role,
        "member_type": user.user_type, "avatar": avatar,
    }


def list_team(company, project) -> list:
    from nucleus.models import ProjectMember

    members = (
        ProjectMember.objects.filter(company=company, project=project, is_active=True)
        .select_related("user", "user__human_profile", "user__persona_profile")
        .order_by("role", "created_at")
    )
    return [_format_member(m) for m in members]


def add_member(company, project, user_id: str, role: str = "member") -> dict:
    from nucleus.models import ProjectMember

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
    from nucleus.models import ProjectMember

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
    company, inviter, email: str, project,
    scope: str = "topic", topic_id: str = None, role: str = "member",
) -> dict:
    from nucleus.models import CompanyAccess, Invitation, ProjectMember

    existing_access = CompanyAccess.objects.filter(
        company=company, user__email=email, is_active=True
    ).select_related("user").first()

    if existing_access:
        user = existing_access.user
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

        if scope == "topic" and topic_id:
            _add_to_topic(company, project, topic_id, user, role)

        return {"ok": True, "is_new_user": False, "email": email, "scope": scope, "message": f"{email} added."}

    if Invitation.objects.filter(
        company=company, email=email, status=Invitation.Status.PENDING, is_active=True
    ).exists():
        raise ValueError(f"{email} has already been invited.")

    token_hash = hashlib.sha256(secrets.token_urlsafe(32).encode()).hexdigest()
    Invitation.objects.create(
        company=company, email=email, role=role, invited_by=inviter,
        token_hash=token_hash, expires_at=timezone.now() + timedelta(days=30),
        access_payload={"project_id": str(project.id)},
    )
    server_url = getattr(settings, "NEURALOPS_SERVER_URL", "").rstrip("/")
    return {
        "ok": True, "is_new_user": True, "email": email, "scope": scope,
        "server_url": server_url or None,
        "message": f"{email} invited. Ask them to sign up and connect to this server.",
    }


def _add_to_topic(company, project, topic_id: str, user, role: str = "participant"):
    from nucleus.models import ChatTopic, TopicParticipant

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
    from nucleus.models import CompanyAccess, ProjectMember
    from django.db.models import Q

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
            "avatar": profile.avatar.url if (profile and profile.avatar) else None,
        })
    return result


def list_available_personas(company, project) -> list:
    from nucleus.models import Persona, ProjectMember

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
            "avatar": p.avatar.url if p.avatar else None,
        }
        for p in personas
    ]


# ── Slug helpers ──────────────────────────────────────────────────────────────

def _unique_project_slug(company, name: str) -> str:
    from nucleus.models import Project
    base = slugify(name) or "project"
    slug, n = base, 1
    while Project.objects.filter(company=company, slug=slug).exists():
        slug = f"{base}-{n}"
        n += 1
    return slug


def _unique_channel_slug(project, name: str) -> str:
    from nucleus.models import Channel
    base = slugify(name) or "channel"
    slug, n = base, 1
    while Channel.objects.filter(project=project, slug=slug).exists():
        slug = f"{base}-{n}"
        n += 1
    return slug


def _unique_topic_slug(channel, title: str) -> str:
    from nucleus.models import ChatTopic
    base = slugify(title) or "topic"
    slug, n = base, 1
    while ChatTopic.objects.filter(channel=channel, slug=slug).exists():
        slug = f"{base}-{n}"
        n += 1
    return slug
