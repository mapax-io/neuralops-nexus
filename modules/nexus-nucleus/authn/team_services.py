"""
Business logic for project team management.
"""
import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()


# ── Formatting helpers ────────────────────────────────────────────────────────

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
        "id": str(member.id),
        "user_id": str(user.id),
        "name": name,
        "email": email,
        "role": member.role,
        "member_type": user.user_type,
        "avatar": avatar,
    }


# ── Team CRUD ─────────────────────────────────────────────────────────────────

def list_team(company, project) -> list:
    """Return all active members of a project (humans + personas)."""
    from nucleus.models import ProjectMember

    members = (
        ProjectMember.objects.filter(company=company, project=project, is_active=True)
        .select_related("user", "user__human_profile", "user__persona_profile")
        .order_by("role", "created_at")
    )
    return [_format_member(m) for m in members]


def add_member(company, project, user_id: str, role: str = "member") -> dict:
    """Add an existing user (human or persona) to a project."""
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


def remove_member(company, project, user_id: str, requesting_user) -> dict:
    """Remove a member from the project (soft-delete)."""
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


# ── Invite (slash command) ────────────────────────────────────────────────────

def invite_to_project(
    company,
    inviter,
    email: str,
    project,
    scope: str = "topic",
    topic_id: str = None,
    role: str = "member",
) -> dict:
    """
    /invite email — pre-authorize an email on this server.

    If the user already exists → add them directly to the project/topic.
    If not → create a pending Invitation (email only, no project payload).
              When they sign up and connect, auth_verify lets them in
              and adds them to all projects automatically.
    """
    from nucleus.models import CompanyAccess, Invitation, ProjectMember

    # Case 1: already on the server — add to project/topic directly
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

        return {
            "ok": True,
            "is_new_user": False,
            "email": email,
            "scope": scope,
            "message": f"{email} added.",
        }

    # Case 2: new user — pre-authorize the email and remember which project
    if Invitation.objects.filter(
        company=company, email=email, status=Invitation.Status.PENDING, is_active=True
    ).exists():
        raise ValueError(f"{email} has already been invited.")

    token_hash = hashlib.sha256(secrets.token_urlsafe(32).encode()).hexdigest()

    Invitation.objects.create(
        company=company,
        email=email,
        role=role,
        invited_by=inviter,
        token_hash=token_hash,
        expires_at=timezone.now() + timedelta(days=30),
        access_payload={"project_id": str(project.id)},
    )

    server_url = getattr(settings, "NEURALOPS_SERVER_URL", "").rstrip("/")

    return {
        "ok": True,
        "is_new_user": True,
        "email": email,
        "scope": scope,
        "server_url": server_url or None,
        "message": f"{email} invited. Ask them to sign up and connect to this server.",
    }


def _add_to_topic(company, project, topic_id: str, user, role: str = "participant"):
    """Add user to a topic as a participant."""
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


# ── Available to add ──────────────────────────────────────────────────────────

def list_available_users(company, project, search: str = "") -> list:
    """Workspace human members not yet in this project."""
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
    """Personas not yet in this project."""
    from nucleus.models import Persona, ProjectMember

    in_project = ProjectMember.objects.filter(
        company=company, project=project, is_active=True,
        user__user_type="persona",
    ).values_list("user_id", flat=True)

    personas = Persona.objects.filter(
        company=company, is_active=True
    ).exclude(identity_user_id__in=in_project).select_related("identity_user")

    result = []
    for p in personas:
        result.append({
            "persona_id": str(p.id),
            "user_id": str(p.identity_user_id),
            "name": p.name,
            "source_type": p.source_type,
            "avatar": p.avatar.url if p.avatar else None,
        })
    return result
