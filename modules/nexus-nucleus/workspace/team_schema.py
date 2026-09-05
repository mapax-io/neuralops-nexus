"""
NOTE: this module (with team_api.py / team_services.py) is NOT mounted --
core/urls.py registers workspace.api's routers only. Dead weight; delete
in a separate pass.
"""
from ninja import Schema
from typing import Optional


class TeamMemberOut(Schema):
    id: str
    user_id: str
    name: str
    email: str
    role: str
    member_type: str
    avatar: Optional[str] = None


class AddMemberRequest(Schema):
    user_id: str
    role: str = "member"


class InviteToProjectRequest(Schema):
    email: str
    scope: str = "topic"
    topic_id: Optional[str] = None
    role: str = "member"


class InviteToProjectOut(Schema):
    ok: bool
    is_new_user: bool
    email: str
    scope: str
    message: str
    server_url: Optional[str] = None


class AvailablePersonaOut(Schema):
    persona_id: str
    user_id: str
    name: str
    avatar: Optional[str] = None
    # REMOVED: source_type -- went away with AIAgent.


class AvailableUserOut(Schema):
    user_id: str
    name: str
    email: str
    avatar: Optional[str] = None
