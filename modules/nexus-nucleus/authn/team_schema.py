from ninja import Schema
from typing import Optional


class TeamMemberOut(Schema):
    id: str            # ProjectMember.id
    user_id: str       # User.id
    name: str          # human full_name or persona name
    email: str         # human email (empty for personas)
    role: str          # owner | admin | member | viewer
    member_type: str   # "human" | "persona"
    avatar: Optional[str] = None


class AddMemberRequest(Schema):
    user_id: str
    role: str = "member"


class InviteToProjectRequest(Schema):
    """Used by the /invite slash command."""
    email: str
    scope: str = "topic"          # "topic" | "project"
    topic_id: Optional[str] = None
    role: str = "member"


class AvailablePersonaOut(Schema):
    persona_id: str
    user_id: str       # identity_user.id  — used to call add_member
    name: str
    source_type: str   # "model" | "agent"
    avatar: Optional[str] = None


class AvailableUserOut(Schema):
    user_id: str
    name: str
    email: str
    avatar: Optional[str] = None
