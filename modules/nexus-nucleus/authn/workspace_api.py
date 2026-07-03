"""
Workspace API — Projects, Channels, Topics.

All endpoints are company-scoped. The company is resolved from the
single Company record on this server (personal/self-hosted mode).

Endpoints:
    GET    /api/v1/projects/                          → list my projects
    POST   /api/v1/projects/                          → create project
    GET    /api/v1/projects/{project_id}/             → get project + channels
    DELETE /api/v1/projects/{project_id}/             → delete project

    GET    /api/v1/projects/{project_id}/channels/            → list channels
    POST   /api/v1/projects/{project_id}/channels/            → create channel

    GET    /api/v1/projects/{project_id}/channels/{channel_id}/topics/   → list topics
    POST   /api/v1/projects/{project_id}/channels/{channel_id}/topics/   → create topic
"""
from typing import List

from ninja import Router
from ninja.errors import HttpError

from .auth import SupabaseBearer
from .workspace_schema import (
    ProjectCreateRequest, ProjectOut, ChannelOut,
    ChannelCreateRequest, TopicCreateRequest, TopicOut,
)
from . import workspace_services as svc

router = Router(tags=["Workspace"], auth=SupabaseBearer())


def _resolve(request):
    """Resolve company + caller. Raises HTTP errors if not valid."""
    user = request.auth

    company = svc.get_company()
    if not company:
        raise HttpError(503, "Server not initialised. Run 'python manage.py create_owner' first.")

    return company, user


def _project_out(project) -> dict:
    channels = project.channel_items.filter(is_active=True).order_by("name")
    return {
        "id": str(project.id),
        "name": project.name,
        "slug": project.slug,
        "description": project.description,
        "channels": [
            {
                "id": str(c.id),
                "name": c.name,
                "slug": c.slug,
                "description": c.description,
            }
            for c in channels
        ],
    }


# ── Projects ──────────────────────────────────────────────────────────────────

@router.get("/", response=List[ProjectOut])
def list_projects(request):
    """List all projects the current user has access to."""
    company, user = _resolve(request)
    projects = svc.list_projects(company, user)
    return [_project_out(p) for p in projects]


@router.post("/", response=ProjectOut)
def create_project(request, payload: ProjectCreateRequest):
    """
    Create a new project.
    Requires add_project permission (owner/admin only).
    Auto-creates a 'general' channel and makes the caller a project admin.
    """
    company, user = _resolve(request)

    if not user.has_perm("nucleus.add_project"):
        raise HttpError(403, "You don't have permission to create projects.")

    try:
        project = svc.create_project(
            company=company,
            user=user,
            name=payload.name,
            description=payload.description,
        )
    except ValueError as exc:
        raise HttpError(400, str(exc))

    return _project_out(project)


@router.get("/{project_id}/", response=ProjectOut)
def get_project(request, project_id: str):
    """Get a single project with its channels."""
    company, user = _resolve(request)

    project = svc.get_project(company, user, project_id)
    if not project:
        raise HttpError(404, "Project not found.")

    return _project_out(project)


@router.delete("/{project_id}/")
def delete_project(request, project_id: str):
    """Delete a project. Requires delete_project permission (owner/admin only)."""
    company, user = _resolve(request)

    if not user.has_perm("nucleus.delete_project"):
        raise HttpError(403, "You don't have permission to delete projects.")

    project = svc.delete_project(company, project_id)
    if not project:
        raise HttpError(404, "Project not found.")

    return {"ok": True, "message": f"Project '{project.name}' deleted."}


# ── Channels ──────────────────────────────────────────────────────────────────

@router.get("/{project_id}/channels/", response=List[ChannelOut])
def list_channels(request, project_id: str):
    """List all channels in a project."""
    company, user = _resolve(request)

    project = svc.get_project(company, user, project_id)
    if not project:
        raise HttpError(404, "Project not found.")

    channels = svc.list_channels(company, project)
    return [
        {"id": str(c.id), "name": c.name, "slug": c.slug, "description": c.description}
        for c in channels
    ]


@router.post("/{project_id}/channels/", response=ChannelOut)
def create_channel(request, project_id: str, payload: ChannelCreateRequest):
    """
    Create a channel inside a project.
    Requires add_channel permission.
    """
    company, user = _resolve(request)

    if not user.has_perm("nucleus.add_channel"):
        raise HttpError(403, "You don't have permission to create channels.")

    project = svc.get_project(company, user, project_id)
    if not project:
        raise HttpError(404, "Project not found.")

    channel = svc.create_channel(
        company=company,
        project=project,
        name=payload.name,
        description=payload.description,
    )
    return {"id": str(channel.id), "name": channel.name, "slug": channel.slug, "description": channel.description}


# ── Topics ────────────────────────────────────────────────────────────────────

@router.get("/{project_id}/channels/{channel_id}/topics/", response=List[TopicOut])
def list_topics(request, project_id: str, channel_id: str):
    """List all topics in a channel."""
    company, user = _resolve(request)

    project = svc.get_project(company, user, project_id)
    if not project:
        raise HttpError(404, "Project not found.")

    channel = svc.get_channel(company, project, channel_id)
    if not channel:
        raise HttpError(404, "Channel not found.")

    topics = svc.list_topics(company, project, channel)
    return [
        {
            "id": str(t.id),
            "title": t.title,
            "slug": t.slug,
            "channel_id": str(t.channel_id),
            "project_id": str(t.project_id),
        }
        for t in topics
    ]


@router.post("/{project_id}/channels/{channel_id}/topics/", response=TopicOut)
def create_topic(request, project_id: str, channel_id: str, payload: TopicCreateRequest):
    """Create a topic inside a channel."""
    company, user = _resolve(request)

    project = svc.get_project(company, user, project_id)
    if not project:
        raise HttpError(404, "Project not found.")

    channel = svc.get_channel(company, project, channel_id)
    if not channel:
        raise HttpError(404, "Channel not found.")

    topic = svc.create_topic(
        company=company,
        project=project,
        channel=channel,
        title=payload.title,
        creator=user,
    )
    return {
        "id": str(topic.id),
        "title": topic.title,
        "slug": topic.slug,
        "channel_id": str(topic.channel_id),
        "project_id": str(topic.project_id),
    }
