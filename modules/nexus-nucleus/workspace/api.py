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
from .schema import (
    ProjectCreateRequest, ProjectOut, ChannelOut, ChannelCreateRequest,
    TopicCreateRequest, TopicOut,
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
def list_projects(request):
    company, user = _resolve(request)
    return [_project_out(p) for p in svc.list_projects(company, user)]


@router.post("/", response=ProjectOut)
def create_project(request, payload: ProjectCreateRequest):
    company, user = _resolve(request)
    if not user.has_perm("nucleus.add_project"):
        raise HttpError(403, "You don't have permission to create projects.")
    try:
        project = svc.create_project(company=company, user=user, name=payload.name, description=payload.description)
    except ValueError as exc:
        raise HttpError(400, str(exc))
    return _project_out(project)


@router.get("/{project_id}/", response=ProjectOut)
def get_project(request, project_id: str):
    company, user = _resolve(request)
    project = svc.get_project(company, user, project_id)
    if not project:
        raise HttpError(404, "Project not found.")
    return _project_out(project)


@router.delete("/{project_id}/")
def delete_project(request, project_id: str):
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
    company, user, project = _resolve_project(request, project_id)
    channels = svc.list_channels(company, project)
    return [{"id": str(c.id), "name": c.name, "slug": c.slug, "description": c.description} for c in channels]


@router.post("/{project_id}/channels/", response=ChannelOut)
def create_channel(request, project_id: str, payload: ChannelCreateRequest):
    company, user, project = _resolve_project(request, project_id)
    if not user.has_perm("nucleus.add_channel"):
        raise HttpError(403, "You don't have permission to create channels.")
    channel = svc.create_channel(company=company, project=project, name=payload.name, description=payload.description)
    return {"id": str(channel.id), "name": channel.name, "slug": channel.slug, "description": channel.description}


# ── Topics ────────────────────────────────────────────────────────────────────

@router.get("/{project_id}/channels/{channel_id}/topics/", response=List[TopicOut])
def list_topics(request, project_id: str, channel_id: str):
    company, user, project = _resolve_project(request, project_id)
    channel = svc.get_channel(company, project, channel_id)
    if not channel:
        raise HttpError(404, "Channel not found.")
    topics = list(svc.list_topics(company, project, channel))
    unread_map = svc.get_topic_unread_map(user, topics)
    return [
        {
            "id": str(t.id), "title": t.title, "slug": t.slug,
            "channel_id": str(t.channel_id), "project_id": str(t.project_id),
            "has_unread": unread_map.get(str(t.id), False),
        }
        for t in topics
    ]


@router.post("/{project_id}/channels/{channel_id}/topics/", response=TopicOut)
def create_topic(request, project_id: str, channel_id: str, payload: TopicCreateRequest):
    company, user, project = _resolve_project(request, project_id)
    channel = svc.get_channel(company, project, channel_id)
    if not channel:
        raise HttpError(404, "Channel not found.")
    topic = svc.create_topic(company=company, project=project, channel=channel, title=payload.title, creator=user)
    return {
        "id": str(topic.id), "title": topic.title, "slug": topic.slug,
        "channel_id": str(topic.channel_id), "project_id": str(topic.project_id),
    }


@router.post("/{project_id}/channels/{channel_id}/topics/{topic_id}/read/", response={200: dict}, tags=["Chat"])
def mark_topic_read(request, project_id: str, channel_id: str, topic_id: str):
    company, user, project = _resolve_project(request, project_id)
    channel = svc.get_channel(company, project, channel_id)
    if not channel:
        raise HttpError(404, "Channel not found.")
    topic = svc.get_topic(company, project, channel, topic_id)
    if not topic:
        raise HttpError(404, "Topic not found.")
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
            company=company, inviter=user, email=payload.email, project=project,
            scope=payload.scope, topic_id=payload.topic_id, role=payload.role,
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
        return svc.send_invite(company, user, payload.email, payload.role)
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
