"""
Members API — invite, list, and remove server members.

Endpoints:
    POST   /api/v1/members/invite/        → send invitation
    GET    /api/v1/members/               → list all members
    DELETE /api/v1/members/{user_id}/     → remove a member
"""
from typing import List

from ninja import Router
from ninja.errors import HttpError

from authn.auth import SupabaseBearer
from .members_schema import InviteRequest, InviteResponse, MemberOut, RemoveMemberResponse
from . import members_services as svc

router = Router(tags=["Members"], auth=SupabaseBearer())


def _require_company(request):
    """Resolve the company and caller's access, raising HTTP errors if not valid."""
    user = request.auth  # set by SupabaseBearer

    company = svc.get_company()
    if not company:
        raise HttpError(503, "Server not initialised. Run 'python manage.py create_owner' first.")

    access = svc.get_member_access(company, user)
    if not access:
        raise HttpError(403, "You are not a member of this server.")

    return company, user, access


@router.post("/invite/", response=InviteResponse)
def invite_member(request, payload: InviteRequest):
    """
    Send an invitation to join this server.
    Requires the **add_invitation** permission (granted to Owner and Admin groups).
    """
    company, user, _ = _require_company(request)

    if not user.has_perm("nucleus.add_invitation"):
        raise HttpError(403, "You don't have permission to invite users.")

    try:
        result = svc.send_invite(company, user, payload.email, payload.role)
    except ValueError as exc:
        raise HttpError(400, str(exc))

    return result


@router.get("/", response=List[MemberOut])
def list_members(request):
    """List all active members of this server."""
    company, _, __ = _require_company(request)
    return svc.list_members(company)


@router.delete("/{user_id}/", response=RemoveMemberResponse)
def remove_member(request, user_id: str):
    """
    Remove a member from this server.
    Requires the **remove_invitation** permission.
    Owners cannot be removed.
    """
    company, user, _ = _require_company(request)

    if not user.has_perm("nucleus.remove_invitation"):
        raise HttpError(403, "You don't have permission to remove members.")

    try:
        result = svc.remove_member(company, user, user_id)
    except ValueError as exc:
        raise HttpError(400, str(exc))

    return result
