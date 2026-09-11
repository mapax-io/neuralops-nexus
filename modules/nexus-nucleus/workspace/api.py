"""
Workspace API — Projects, Channels, Topics, Members, and Team.
Two routers:
  - router        → mounted at /projects/
  - members_router → mounted at /members/
"""
from typing import List, Optional

from ninja import Router, Query
from ninja.errors import HttpError

from authn.auth import SupabaseBearer
from authn.permissions.checker import PermissionChecker
from .schema import (
    ProjectCreateRequest, ProjectOut, ChannelOut, ChannelCreateRequest,
    TopicCreateRequest, TopicUpdateRequest, TopicOut,
    InviteRequest, InviteResponse, MemberOut, RemoveMemberResponse,
    TeamMemberOut, AddMemberRequest, InviteToProjectRequest, InviteToProjectOut,
    AvailableUserOut, AvailablePersonaOut,
)
from . import services as svc

router = Router(tags=["Workspace"], auth=SupabaseBearer())
members_router = Router(tags=["Members"], auth=SupabaseBearer())


# ── Helpers ───────────────────────────────────────────────────────────────────

def _resolve(request):
    user = request.auth
    company = svc.get_company()
    if not company:
        raise HttpError(503, "Server not initialised. Run 'python manage.py create_owner' first.")
    return company, user


def _resolve_project(request, project_id: str):
    company, user = _resolve(request)
    project = svc.get_project(company, user, project_id)
    if not project:
        raise HttpError(404, "Project not found.")
    return company, user, project


def _project_out(project) -> dict:
    channels = project.channel_items.filter(is_active=True).order_by("name")
    return {
        "id": str(project.id),
        "name": project.name,
        "slug": project.slug,
        "description": project.description,
        "channels": [
            {"id": str(c.id), "name": c.name, "slug": c.slug, "description": c.description}
            for c in channels
        ],
    }


# ── Projects ──────────────────────────────────────────────────────────────────

@router.get("/", response=List[ProjectOut])
def list_projects(request, include_archived: bool = Query(default=False)):
    company, user = _resolve(request)
    return [_project_out(p) for p in svc.list_projects(company, user, include_archived=include_archived)]


@router.post("/", response=ProjectOut)
def create_project(request, payload: ProjectCreateRequest):
    company, user = _resolve(request)
    if not PermissionChecker.can(user, "project.create", company=company):
        raise HttpError(403, "You don't have permission to create projects.")
    try:
        project = svc.create_project(company=company, user=user, name=payload.name, 
                                     description=payload.description)
    except ValueError as exc:
        raise HttpError(400, str(exc))
    svc.provision_project_folder_and_mcp(project)
    return _project_out(project)


@router.get("/{project_id}/", response=ProjectOut)
def get_project(request, project_id: str):
    company, user = _resolve(request)
    project = svc.get_project(company, user, project_id)
    if not project:
        raise HttpError(404, "Project not found.")
    return _project_out(project)


@router.delete("/{project_id}/")
def archive_project(request, project_id: str):
    company, user = _resolve(request)
    # Fetch first (no permission filtering) so a 404 vs 403 distinction is
    # possible: object doesn't exist at all, vs. exists but you can't archive it.
    project = svc.get_project_object(company, project_id)
    if not project:
        raise HttpError(404, "Project not found.")
    if not PermissionChecker.can(user, "project.archive", obj=project):
        raise HttpError(403, "You don't have permission to archive this project.")
    svc.archive_project(project)
    return {"ok": True, "message": f"Project '{project.name}' archived."}


# ── Channels ──────────────────────────────────────────────────────────────────

@router.get("/{project_id}/channels/", response=List[ChannelOut])
def list_channels(request, project_id: str, include_archived: bool = Query(default=False)):
    company, user, project = _resolve_project(request, project_id)
    channels = svc.list_channels(user, project, include_archived=include_archived)
    return [{"id": str(c.id), "name": c.name, "slug": c.slug, "description": c.description} for c in channels]


@router.post("/{project_id}/channels/", response=ChannelOut)
def create_channel(request, project_id: str, payload: ChannelCreateRequest):
    company, user, project = _resolve_project(request, project_id)
    if not PermissionChecker.can(user, "channel.create", obj=project):
        raise HttpError(403, "You don't have permission to create channels.")
    channel = svc.create_channel(company=company, project=project, name=payload.name, description=payload.description)
    return {"id": str(channel.id), "name": channel.name, "slug": channel.slug, "description": channel.description}


@router.post("/{project_id}/channels/{channel_id}/archive/", response={200: dict})
def archive_channel(request, project_id: str, channel_id: str):
    company, user, project = _resolve_project(request, project_id)
    channel = svc.get_channel(company, project, channel_id)
    if not channel:
        raise HttpError(404, "Channel not found.")
    if not PermissionChecker.can(user, "channel.archive", obj=channel):
        raise HttpError(403, "You don't have permission to archive this channel.")
    svc.archive_channel(channel)
    return {"ok": True, "message": f"Channel '{channel.name}' archived."}


# ── Topics ────────────────────────────────────────────────────────────────────

@router.get("/{project_id}/channels/{channel_id}/topics/", response=List[TopicOut])
def list_topics(request, project_id: str, channel_id: str, include_archived: bool = Query(default=False)):
    company, user, project = _resolve_project(request, project_id)
    channel = svc.get_channel(company, project, channel_id)
    if not channel:
        raise HttpError(404, "Channel not found.")
    topics = list(svc.list_topics(user, channel, include_archived=include_archived))
    unread_map = svc.get_topic_unread_map(user, topics)
    return [
        {
            "id": str(t.id), "title": t.title, "slug": t.slug,
            "channel_id": str(t.channel_id), "project_id": str(t.project_id),
            "has_unread": unread_map.get(str(t.id), 0) > 0,
            "unread_count": unread_map.get(str(t.id), 0),
        }
        for t in topics
    ]


@router.post("/{project_id}/channels/{channel_id}/topics/", response=TopicOut)
def create_topic(request, project_id: str, channel_id: str, payload: TopicCreateRequest):
    company, user, project = _resolve_project(request, project_id)
    channel = svc.get_channel(company, project, channel_id)
    if not channel:
        raise HttpError(404, "Channel not found.")
    if not PermissionChecker.can(user, "topic.create", obj=channel):
        raise HttpError(403, "You don't have permission to create topics in this channel.")
    topic = svc.create_topic(company=company, project=project, channel=channel, title=payload.title, creator=user)
    return {
        "id": str(topic.id), "title": topic.title, "slug": topic.slug,
        "channel_id": str(topic.channel_id), "project_id": str(topic.project_id),
    }


@router.patch("/{project_id}/channels/{channel_id}/topics/{topic_id}/", response=TopicOut)
def update_topic(request, project_id: str, channel_id: str, topic_id: str, payload: TopicUpdateRequest):
    company, user, project = _resolve_project(request, project_id)
    channel = svc.get_channel(company, project, channel_id)
    if not channel:
        raise HttpError(404, "Channel not found.")
    topic = svc.get_topic(company, project, channel, topic_id)
    if not topic:
        raise HttpError(404, "Topic not found.")
    if not PermissionChecker.can(user, "topic.update", obj=topic):
        raise HttpError(403, "You don't have permission to rename this topic.")
    topic = svc.update_topic(project, channel, topic, payload.title)
    return {
        "id": str(topic.id), "title": topic.title, "slug": topic.slug,
        "channel_id": str(topic.channel_id), "project_id": str(topic.project_id),
    }


@router.post("/{project_id}/channels/{channel_id}/topics/{topic_id}/archive/", response={200: dict})
def archive_topic(request, project_id: str, channel_id: str, topic_id: str):
    company, user, project = _resolve_project(request, project_id)
    channel = svc.get_channel(company, project, channel_id)
    if not channel:
        raise HttpError(404, "Channel not found.")
    topic = svc.get_topic(company, project, channel, topic_id)
    if not topic:
        raise HttpError(404, "Topic not found.")
    if not PermissionChecker.can(user, "topic.archive", obj=topic):
        raise HttpError(403, "You don't have permission to archive this topic.")
    svc.archive_topic(topic)
    return {"ok": True, "message": f"Topic '{topic.title}' archived."}


@router.post("/{project_id}/channels/{channel_id}/topics/{topic_id}/read/", response={200: dict}, tags=["Chat"])
def mark_topic_read(request, project_id: str, channel_id: str, topic_id: str):
    company, user, project = _resolve_project(request, project_id)
    channel = svc.get_channel(company, project, channel_id)
    if not channel:
        raise HttpError(404, "Channel not found.")
    topic = svc.get_topic(company, project, channel, topic_id)
    if not topic:
        raise HttpError(404, "Topic not found.")
    if not PermissionChecker.can(user, "topic.mark_read", obj=topic):
        raise HttpError(403, "You don't have permission to do that here.")
    svc.mark_topic_read(user, topic)
    return {"ok": True}


# ── Team ──────────────────────────────────────────────────────────────────────

@router.get("/{project_id}/team/", response=List[TeamMemberOut])
def list_team(request, project_id: str):
    company, user, project = _resolve_project(request, project_id)
    return svc.list_team(company, project)


@router.post("/{project_id}/team/", response=TeamMemberOut)
def add_member(request, project_id: str, payload: AddMemberRequest):
    company, user, project = _resolve_project(request, project_id)
    try:
        return svc.add_member(company, project, payload.user_id, payload.role)
    except ValueError as exc:
        raise HttpError(400, str(exc))


@router.post("/{project_id}/team/invite/", response=InviteToProjectOut)
def invite_to_project(request, project_id: str, payload: InviteToProjectRequest):
    company, user, project = _resolve_project(request, project_id)
    try:
        return svc.invite_to_project(
            company=company, inviter=user, project=project,
            email=payload.email, persona_name=payload.persona_name,
            scope=payload.scope, topic_id=payload.topic_id, role=payload.role,
            redirect_to=payload.redirect_to,
        )
    except ValueError as exc:
        raise HttpError(400, str(exc))


@router.get("/{project_id}/team/available-users/", response=List[AvailableUserOut])
def available_users(request, project_id: str, search: Optional[str] = Query(default="")):
    company, user, project = _resolve_project(request, project_id)
    return svc.list_available_users(company, project, search)


@router.get("/{project_id}/team/available-personas/", response=List[AvailablePersonaOut])
def available_personas(request, project_id: str):
    company, user, project = _resolve_project(request, project_id)
    return svc.list_available_personas(company, project)


@router.delete("/{project_id}/team/{user_id}/")
def remove_team_member(request, project_id: str, user_id: str):
    company, user, project = _resolve_project(request, project_id)
    try:
        return svc.remove_team_member(company, project, user_id, user)
    except ValueError as exc:
        raise HttpError(400, str(exc))


@router.delete("/server/members/{user_id}/", tags=["Server"])
def remove_from_server(request, user_id: str):
    company, user = _resolve(request)
    try:
        return svc.remove_user_from_server(company, user_id, user)
    except ValueError as exc:
        raise HttpError(400, str(exc))


# ── Members router (/members/ prefix) ────────────────────────────────────────

def _require_company(request):
    user = request.auth
    company = svc.get_company()
    if not company:
        raise HttpError(503, "Server not initialised. Run 'python manage.py create_owner' first.")
    access = svc.get_member_access(company, user)
    if not access:
        raise HttpError(403, "You are not a member of this server.")
    return company, user, access


@members_router.post("/invite/", response=InviteResponse)
def invite_member(request, payload: InviteRequest):
    company, user, _ = _require_company(request)
    if not user.has_perm("nucleus.add_invitation"):
        raise HttpError(403, "You don't have permission to invite users.")
    try:
        return svc.invite_to_system(
            company, user, payload.email, payload.role,
            grants=[dict(g) for g in payload.grants], redirect_to=payload.redirect_to,
        )
    except ValueError as exc:
        raise HttpError(400, str(exc))


@members_router.get("/", response=List[MemberOut])
def list_members(request):
    company, _, __ = _require_company(request)
    return svc.list_members(company)


@members_router.delete("/{user_id}/", response=RemoveMemberResponse)
def remove_member(request, user_id: str):
    company, user, _ = _require_company(request)
    if not user.has_perm("nucleus.remove_invitation"):
        raise HttpError(403, "You don't have permission to remove members.")
    try:
        return svc.remove_member(company, user, user_id)
    except ValueError as exc:
        raise HttpError(400, str(exc))
