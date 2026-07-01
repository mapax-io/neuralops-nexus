"""
Business logic for Projects, Channels, and Topics.
All queries are scoped to company — safe for multi-tenant / SaaS use.
"""
from django.utils.text import slugify


def get_company():
    from nucleus.models import Company
    return Company.objects.filter(is_active=True).first()


# ── Projects ──────────────────────────────────────────────────────────────────

def list_projects(company, user):
    """
    Return all projects the user is a member of.
    Server owner/admin can see all projects.
    """
    from nucleus.models import Project, CompanyAccess

    access = CompanyAccess.objects.filter(
        company=company, user=user, is_active=True
    ).first()

    if access and access.role in ("owner", "admin"):
        # Owner and admin see all company projects
        return Project.objects.filter(company=company, is_active=True).order_by("name")

    # Members/viewers see only projects they belong to
    return Project.objects.filter(
        company=company,
        is_active=True,
        projectmember_items__user=user,
        projectmember_items__is_active=True,
    ).distinct().order_by("name")


def create_project(company, user, name: str, description: str = None):
    """
    Create a project, auto-create 'general' channel, add creator as admin.
    Raises ValueError on duplicate slug.
    """
    from nucleus.models import Project, Channel, ProjectMember

    slug = _unique_project_slug(company, name)

    project = Project.objects.create(
        company=company,
        name=name,
        slug=slug,
        description=description or "",
    )

    # Auto-create general channel
    Channel.objects.create(
        company=company,
        project=project,
        name="general",
        slug="general",
        description="General discussion",
    )

    # Creator becomes project admin
    ProjectMember.objects.create(
        company=company,
        project=project,
        user=user,
        role=ProjectMember.Role.ADMIN,
    )

    return project


def get_project(company, user, project_id: str):
    """Get a single project the user has access to."""
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

    # Check project membership
    if project.projectmember_items.filter(user=user, is_active=True).exists():
        return project

    return None


def delete_project(company, project_id: str):
    """Soft-delete a project."""
    from nucleus.models import Project

    project = Project.objects.filter(
        company=company, id=project_id, is_active=True
    ).first()
    if project:
        project.soft_delete()
    return project


# ── Channels ──────────────────────────────────────────────────────────────────

def list_channels(company, project):
    return project.channel_items.filter(
        company=company, is_active=True
    ).order_by("name")


def create_channel(company, project, name: str, description: str = None):
    """Create a channel inside a project."""
    from nucleus.models import Channel

    slug = _unique_channel_slug(project, name)

    return Channel.objects.create(
        company=company,
        project=project,
        name=name,
        slug=slug,
        description=description or "",
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
    """Create a topic inside a channel."""
    from nucleus.models import ChatTopic

    slug = _unique_topic_slug(channel, title)

    return ChatTopic.objects.create(
        company=company,
        project=project,
        channel=channel,
        title=title,
        slug=slug,
    )


def get_topic(company, project, channel, topic_id: str):
    from nucleus.models import ChatTopic
    return ChatTopic.objects.filter(
        company=company, project=project, channel=channel,
        id=topic_id, is_active=True
    ).first()


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
