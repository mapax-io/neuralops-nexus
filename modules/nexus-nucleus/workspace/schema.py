from typing import Optional, List
from ninja import Schema


# ── Projects / Channels / Topics ──────────────────────────────────────────────

class ProjectCreateRequest(Schema):
    name: str
    description: Optional[str] = None


class ChannelOut(Schema):
    id: str
    name: str
    slug: str
    description: Optional[str] = None


class ProjectOut(Schema):
    id: str
    name: str
    slug: str
    description: Optional[str] = None
    channels: List[ChannelOut] = []


class ChannelCreateRequest(Schema):
    name: str
    description: Optional[str] = None


class TopicCreateRequest(Schema):
    title: str


class TopicOut(Schema):
    id: str
    title: str
    slug: str
    channel_id: str
    project_id: str
    has_unread: bool = False


# ── Members ───────────────────────────────────────────────────────────────────

class InviteRequest(Schema):
    email: str
    role: str = "member"


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


# ── Team ──────────────────────────────────────────────────────────────────────

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


class AvailableUserOut(Schema):
    user_id: str
    name: str
    email: str
    avatar: Optional[str] = None


class AvailablePersonaOut(Schema):
    persona_id: str
    user_id: str
    name: str
    source_type: str
    avatar: Optional[str] = None
