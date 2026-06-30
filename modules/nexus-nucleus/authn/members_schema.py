from typing import Optional
from ninja import Schema


class InviteRequest(Schema):
    email: str
    role: str = "member"  # owner | admin | member | viewer


class InviteResponse(Schema):
    ok: bool
    message: str
    email: str
    role: str
    expires_at: str


class MemberOut(Schema):
    user_id: str
    email: str
    role: str
    invited_by: Optional[str] = None
    joined_at: str


class RemoveMemberResponse(Schema):
    ok: bool
    message: str
