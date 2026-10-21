"""
Workspace API — Projects, Channels, Topics, Members, and Team.
Two routers:
  - router        → mounted at /projects/
  - members_router → mounted at /members/
"""
from typing import List, Optional

from ninja import Router, Query, Schema
from ninja.errors import HttpError

from authn.auth import SupabaseBearer
from authn.permissions.checker import PermissionChecker
from workspace import deliverables
from .schema import (
    MemberAccessOut, SetMemberAccessIn,
    ProjectCreateRequest, ProjectUpdateRequest, ProjectOut, ChannelOut, ChannelCreateRequest,
    TopicCreateRequest, TopicUpdateRequest, TopicOut,
    InviteRequest, InviteResponse, MemberOut, RemoveMemberResponse,
    TeamMemberOut, AddMemberRequest, InviteToProjectRequest, InviteToProjectOut,
    AvailableUserOut, AvailablePersonaOut,
    BrowserSessionIn,
    DeliverableKeepIn,
    DeliverableOut,
    TerminalSessionOut,
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


def _require_team_manager(user, project):
    # Who may add, invite and remove people on a project: the right the app's
    # team dialog already draws its controls from. A dedicated
    # project.invite_member / project.remove_member pair is the documented
    # follow-up (docs/CONCEPTS-AND-ROLES.md, Part 5).
    if not PermissionChecker.can(user, "project.archive", obj=project):
        raise HttpError(403, "You don't have permission to manage this project's team.")


def _project_out(project, with_brief: bool = False) -> dict:
    channels = project.channel_items.filter(is_active=True).order_by("name")
    # The project-wide default router; a retired model reads as none (the
    # internal API skips it the same way — the seat just stays unfilled).
    router = project.default_router_model
    if router is not None and not router.is_active:
        router = None
    return {
        "brief": project.brief if with_brief and project.brief else None,
        "brief_length": len(project.brief or ""),
        "id": str(project.id),
        "name": project.name,
        "slug": project.slug,
        "description": project.description,
        "default_router_model": {"id": str(router.id), "name": router.name} if router else None,
        # Money is a decimal STRING on the wire, never a float. The month's
        # spend costs one aggregate query, so it rides the DETAIL route only.
        "spend_limit_monthly": str(project.spend_limit_monthly) if project.spend_limit_monthly is not None else None,
        "spent_this_month": str(svc.spend_this_month(project)) if with_brief else None,
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
    # The four built-in routines every project starts with (W4).
    from intelligence.services import seed_builtin_routines
    seed_builtin_routines(project)
    return _project_out(project)


@router.get("/{project_id}/", response=ProjectOut)
def get_project(request, project_id: str):
    company, user = _resolve(request)
    project = svc.get_project(company, user, project_id)
    if not project:
        raise HttpError(404, "Project not found.")
    return _project_out(project, with_brief=True)


@router.patch("/{project_id}/", response=ProjectOut)
def update_project(request, project_id: str, payload: ProjectUpdateRequest):
    company, user = _resolve(request)
    project = svc.get_project_object(company, project_id)
    if not project:
        raise HttpError(404, "Project not found.")
    if not PermissionChecker.can(user, "project.update", obj=project):
        raise HttpError(403, "You don't have permission to edit this project.")
    try:
        svc.update_project(
            project, user, brief=payload.brief, description=payload.description,
            default_router_model_id=payload.default_router_model_id,
            clear_default_router=payload.clear_default_router,
            spend_limit_monthly=payload.spend_limit_monthly,
            clear_spend_limit=payload.clear_spend_limit,
        )
    except ValueError as exc:
        raise HttpError(400, str(exc))
    return _project_out(project, with_brief=True)


# ── Embedder (Step 3, handoff change 10) ──────────────────────────────

EMBEDDER_PROVIDERS = ("fastembed", "openai_compatible", "hash")


class EmbedderIn(Schema):
    # a bare `payload: dict` reads as a QUERY param in ninja — the body needs
    # a Schema. {embedder: null} = back to the system default.
    embedder: Optional[dict] = None


@router.get("/{project_id}/embedder/", response=dict)
def get_project_embedder(request, project_id: str):
    """The project's embedder spec (null = the system default, local fastembed)
    and whether its memory is rebuilding right now."""
    company, user = _resolve(request)
    project = svc.get_project(company, user, project_id)
    if not project:
        raise HttpError(404, "Project not found.")
    return {"embedder": project.embedder, "reindex_status": project.reindex_status}


@router.put("/{project_id}/embedder/", response=dict)
def set_project_embedder(request, project_id: str, payload: EmbedderIn):
    """
    Change the project's embedding model (company owner/admin only — decision
    8). Saving it LOCKS the project (persona triggers are refused) and starts
    the rebuild: every vector is re-embedded with the new model; the old index
    stays active underneath, so a crash is safe and re-saving retries.
    Body: {"embedder": {provider, model_id, api_base?, api_key?} | null}
    (null = back to the system default).
    """
    company, user = _resolve(request)
    project = svc.get_project_object(company, project_id)
    if not project:
        raise HttpError(404, "Project not found.")
    if not PermissionChecker.can(user, "project.embedder", obj=project):
        raise HttpError(403, "Only a company owner or admin can change a project's embedding model.")
    if project.reindex_status == "building":
        raise HttpError(409, "This project's memory is already rebuilding; wait for it to finish.")

    spec = payload.embedder
    if spec is not None:
        if not isinstance(spec, dict) or spec.get("provider") not in EMBEDDER_PROVIDERS:
            raise HttpError(400, f"embedder.provider must be one of {', '.join(EMBEDDER_PROVIDERS)}.")
        if not (spec.get("model_id") or "").strip():
            raise HttpError(400, "embedder.model_id is required.")

    project.embedder = spec
    project.reindex_status = "building"
    project.save(update_fields=["embedder", "reindex_status"])

    from intelligence.tasks import reindex_project
    reindex_project.delay(str(project.id))
    return {"embedder": project.embedder, "reindex_status": "building"}


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

# ── File viewer (Step 5, docs/NUCLEUS-REVAMP.md §3) ──
# Browse, download, view-as-HTML over the project's folder — the same folder
# the personas' filesystem tools write into. Reading needs the project (the
# same project.view road every other read uses); paths are walled inside the
# project folder in workspace/files.py.

from django.http import FileResponse, HttpResponse

from workspace import files as file_viewer


@router.get("/{project_id}/files/", response=dict)
def list_project_files(request, project_id: str, path: str = Query(default="")):
    """The folder's entries (folders first), relative to the project folder."""
    company, user, project = _resolve_project(request, project_id)
    try:
        return file_viewer.list_folder(project, path)
    except file_viewer.FileViewerError as exc:
        raise HttpError(exc.status, str(exc))


@router.get("/{project_id}/files/content/")
def get_project_file(request, project_id: str, path: str = Query(...), as_: str = Query(default="", alias="as")):
    """
    The file itself. Plain call = a download (streamed, any size).
    `?as=html` = a self-contained view page (markdown rendered, code
    highlighted, images shown) — size-capped, and served with CSP `sandbox`
    so nothing a file carries can run in the viewer's browser.
    """
    company, user, project = _resolve_project(request, project_id)
    try:
        if as_ == "html":
            response = HttpResponse(file_viewer.render_html(project, path))
            response["Content-Security-Policy"] = "sandbox"
            response["X-Content-Type-Options"] = "nosniff"
            return response
        file_path, content_type = file_viewer.open_for_download(project, path)
        return FileResponse(
            open(file_path, "rb"), as_attachment=True,
            filename=file_path.name, content_type=content_type,
        )
    except file_viewer.FileViewerError as exc:
        raise HttpError(exc.status, str(exc))


@router.post("/{project_id}/terminal/session/", response=TerminalSessionOut)
def open_terminal_session(request, project_id: str):
    """
    Terminal (W21): a ticket for a shell session in the project's folder on
    the server, for whoever holds project.terminal. The app connects to the
    worker's WebSocket with it (see workspace/services.py).
    """
    company, user = _resolve(request)
    project = svc.get_project_object(company, project_id)
    if not project:
        raise HttpError(404, "Project not found.")
    if not PermissionChecker.can(user, "project.terminal", obj=project):
        raise HttpError(403, "You don't have permission to open a terminal in this project.")
    try:
        return svc.open_terminal_session(project, user)
    except svc.TerminalError as exc:
        raise HttpError(exc.status, str(exc))


@router.post("/{project_id}/browser/session/", response=TerminalSessionOut)
def open_browser_session(request, project_id: str, payload: BrowserSessionIn):
    """
    The live browser: a ticket for a real Chromium on the server, for whoever
    holds project.browser. Admin-tier on purpose — a browser running inside the
    deployment can reach whatever the server can, so it is not a member's tool.
    """
    company, user = _resolve(request)
    project = svc.get_project_object(company, project_id)
    if not project:
        raise HttpError(404, "Project not found.")
    if not PermissionChecker.can(user, "project.browser", obj=project):
        raise HttpError(403, "You don't have permission to open the browser in this project.")
    try:
        return svc.open_browser_session(project, user, width=payload.width, height=payload.height, url=payload.url)
    except svc.BrowserError as exc:
        raise HttpError(exc.status, str(exc))


def ws_visible_topic(user, project, topic_id) -> bool:
    """Whether this person can see that topic -- the same row visibility every chat route uses."""
    from authn.permissions.row_rules import visible_topic

    return visible_topic(user, project, topic_id) is not None


# ── Deliverables (W10) ────────────────────────────────────────────────────────
# What a persona produced and the team kept: a chart, a page, a table, a form.
# Reading needs the project; keeping and removing need deliverable.manage.

@router.get("/{project_id}/deliverables/", response=List[DeliverableOut])
def list_deliverables(request, project_id: str, latest: bool = Query(default=False), title: Optional[str] = None):
    """The kept things, newest version of each first. Content is left out until one is opened."""
    company, user, project = _resolve_project(request, project_id)
    rows = deliverables.list_deliverables(project, title=title, latest_only=latest)
    return [deliverables.summary(r) for r in rows]


@router.get("/{project_id}/deliverables/{deliverable_id}/", response=DeliverableOut)
def get_deliverable(request, project_id: str, deliverable_id: str):
    company, user, project = _resolve_project(request, project_id)
    row = deliverables.get_deliverable(project, deliverable_id)
    if not row:
        raise HttpError(404, "Deliverable not found.")
    return deliverables.serialise(row)


@router.post("/{project_id}/deliverables/", response=DeliverableOut)
def keep_deliverable(request, project_id: str, payload: DeliverableKeepIn):
    """Keep a reply under a name. The same name again is a new version, never an overwrite."""
    from nucleus.models import ChatMessage

    company, user, project = _resolve_project(request, project_id)
    if not PermissionChecker.can(user, "deliverable.manage", obj=project):
        raise HttpError(403, "You don't have permission to keep deliverables in this project.")
    message = ChatMessage.objects.filter(id=payload.message_id, project=project, is_active=True).first()
    if not message:
        raise HttpError(404, "Message not found.")
    # A topic the person cannot see is a message they cannot keep.
    if not ws_visible_topic(user, project, message.topic_id):
        raise HttpError(404, "Message not found.")
    metadata = message.metadata or {}
    try:
        return deliverables.serialise(deliverables.keep(
            company, project, user,
            title=payload.title,
            kind=metadata.get("render_as") or metadata.get("output_type") or "text",
            content=message.content or "",
            source_message=message,
        ))
    except deliverables.DeliverableError as exc:
        raise HttpError(exc.status, str(exc))


@router.delete("/{project_id}/deliverables/{deliverable_id}/", response={204: None})
def delete_deliverable(request, project_id: str, deliverable_id: str):
    company, user, project = _resolve_project(request, project_id)
    if not PermissionChecker.can(user, "deliverable.manage", obj=project):
        raise HttpError(403, "You don't have permission to remove deliverables in this project.")
    row = deliverables.get_deliverable(project, deliverable_id)
    if not row:
        raise HttpError(404, "Deliverable not found.")
    deliverables.delete_deliverable(row)
    return 204, None


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
    _require_team_manager(user, project)
    try:
        return svc.add_member(company, project, payload.user_id, payload.role)
    except ValueError as exc:
        raise HttpError(400, str(exc))


@router.post("/{project_id}/team/invite/", response=InviteToProjectOut)
def invite_to_project(request, project_id: str, payload: InviteToProjectRequest):
    company, user, project = _resolve_project(request, project_id)
    _require_team_manager(user, project)
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
    _require_team_manager(user, project)
    try:
        return svc.remove_team_member(company, project, user_id, user)
    except ValueError as exc:
        raise HttpError(400, str(exc))


@router.delete("/server/members/{user_id}/", tags=["Server"])
def remove_from_server(request, user_id: str):
    company, user = _resolve(request)
    if not PermissionChecker.can(user, "company.remove_member", company=company):
        raise HttpError(403, "You don't have permission to remove members.")
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


def _require_member_manager(user, company):
    # The right, not the legacy group -- the same gate the Members page draws
    # its controls from.
    if not PermissionChecker.can(user, "company.invite_member", company=company):
        raise HttpError(403, "You don't have permission to manage members.")


@members_router.get("/{user_id}/access/", response=MemberAccessOut)
def member_access(request, user_id: str):
    company, user, _ = _require_company(request)
    _require_member_manager(user, company)
    target = svc.get_member(company, user_id)
    if not target:
        raise HttpError(404, "Member not found.")
    return svc.member_access(company, target)


@members_router.put("/{user_id}/access/", response=MemberAccessOut)
def set_member_access(request, user_id: str, payload: SetMemberAccessIn):
    company, user, _ = _require_company(request)
    _require_member_manager(user, company)
    try:
        return svc.set_member_access(company, user, user_id, payload.role, [dict(g) for g in payload.grants])
    except ValueError as exc:
        raise HttpError(400, str(exc))


@members_router.delete("/{user_id}/", response=RemoveMemberResponse)
def remove_member(request, user_id: str):
    company, user, _ = _require_company(request)
    if not user.has_perm("nucleus.remove_invitation"):
        raise HttpError(403, "You don't have permission to remove members.")
    try:
        return svc.remove_member(company, user, user_id)
    except ValueError as exc:
        raise HttpError(400, str(exc))
