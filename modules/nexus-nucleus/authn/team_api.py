"""
Team API — manage project members (humans + personas).

Endpoints:
    GET    /api/v1/projects/{project_id}/team/                     → list team
    POST   /api/v1/projects/{project_id}/team/                     → add member
    DELETE /api/v1/projects/{project_id}/team/{user_id}/           → remove member
    POST   /api/v1/projects/{project_id}/team/invite/              → /invite slash command
    GET    /api/v1/projects/{project_id}/team/available-users/     → workspace users not in project
    GET    /api/v1/projects/{project_id}/team/available-personas/  → personas not in project
"""
from typing import List, Optional

from ninja import Router, Query
from ninja.errors import HttpError

from .auth import SupabaseBearer
from .team_schema import (
    TeamMemberOut, AddMemberRequest, InviteToProjectRequest,
    AvailableUserOut, AvailablePersonaOut,
)
from . import team_services as svc
from . import workspace_services as ws_svc

router = Router(tags=["Team"], auth=SupabaseBearer())


def _resolve(request, project_id: str):
    """Resolve company, user, and project. Raises HTTP errors if not valid."""
    user = request.auth

    company = ws_svc.get_company()
    if not company:
        raise HttpError(503, "Server not initialised.")

    project = ws_svc.get_project(company, user, project_id)
    if not project:
        raise HttpError(404, "Project not found.")

    return company, user, project


# ── List team ─────────────────────────────────────────────────────────────────

@router.get("/{project_id}/team/", response=List[TeamMemberOut])
def list_team(request, project_id: str):
    """List all members of a project (humans + personas)."""
    company, user, project = _resolve(request, project_id)
    return svc.list_team(company, project)


# ── Add member ────────────────────────────────────────────────────────────────

@router.post("/{project_id}/team/", response=TeamMemberOut)
def add_member(request, project_id: str, payload: AddMemberRequest):
    """Add an existing workspace user or persona to this project."""
    company, user, project = _resolve(request, project_id)

    try:
        return svc.add_member(company, project, payload.user_id, payload.role)
    except ValueError as exc:
        raise HttpError(400, str(exc))


# ── /invite slash command (must be before /{user_id}/ to avoid route conflict) ─

@router.post("/{project_id}/team/invite/")
def invite_to_project(request, project_id: str, payload: InviteToProjectRequest):
    """
    Handle the /invite slash command from the chat input.
    - Existing workspace user → add directly to project/topic
    - New user → create invitation + send email with server link
    Returns a message used to generate a system message in the topic.
    """
    company, user, project = _resolve(request, project_id)

    try:
        result = svc.invite_to_project(
            company=company,
            inviter=user,
            email=payload.email,
            project=project,
            scope=payload.scope,
            topic_id=payload.topic_id,
            role=payload.role,
        )
    except ValueError as exc:
        raise HttpError(400, str(exc))

    return result


# ── Available to add (must be before /{user_id}/ to avoid route conflict) ─────

@router.get("/{project_id}/team/available-users/", response=List[AvailableUserOut])
def available_users(request, project_id: str, search: Optional[str] = Query(default="")):
    """List workspace human users not yet in this project. Optional search."""
    company, user, project = _resolve(request, project_id)
    return svc.list_available_users(company, project, search)


@router.get("/{project_id}/team/available-personas/", response=List[AvailablePersonaOut])
def available_personas(request, project_id: str):
    """List personas not yet in this project."""
    company, user, project = _resolve(request, project_id)
    return svc.list_available_personas(company, project)


# ── Remove member (parameterised — must be LAST to not shadow literal paths) ──

@router.delete("/{project_id}/team/{user_id}/")
def remove_member(request, project_id: str, user_id: str):
    """Remove a member from the project."""
    company, user, project = _resolve(request, project_id)

    try:
        return svc.remove_member(company, project, user_id, user)
    except ValueError as exc:
        raise HttpError(400, str(exc))
