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


class TopicUpdateRequest(Schema):
    title: str


class TopicOut(Schema):
    id: str
    title: str
    slug: str
    channel_id: str
    project_id: str
    has_unread: bool = False
    unread_count: int = 0


# ── Members ───────────────────────────────────────────────────────────────────

class GrantIn(Schema):
    project_id: str
    # Empty = the whole project: one project-scope assignment, which also
    # reaches topics created later. Ids = only those topics, each its own
    # topic-scope assignment (they cannot see sibling topics).
    topic_ids: List[str] = []


class InviteRequest(Schema):
    email: str
    role: str = "member"
    # Where the invitation email lands the invitee (the web app's password
    # page). Used only when the server holds SUPABASE_SERVICE_KEY.
    redirect_to: Optional[str] = None
    # Projects/topics to add them to as well, with the same role. Applied at
    # once for an existing user, at acceptance for a brand-new one.
    grants: List[GrantIn] = []


class InviteResponse(Schema):
    ok: bool
    message: str
    email: str
    role: str
    # invite_to_system() has always returned is_new_user; the schema dropped it.
    is_new_user: bool = False
    # Whether the invitee was emailed (needs the service key); email_note says
    # why not otherwise.
    email_sent: bool = False
    email_note: Optional[str] = None
    # Optional now that invite_to_system() has two non-pending outcomes
    # (already a member / granted immediately) with no Invitation row,
    # hence no expiry -- only the "brand new person, pending invite"
    # outcome sets this. See #120.
    expires_at: Optional[str] = None
    # What was granted (or stored for acceptance). Echoed so a client can tell
    # a server that understood `grants` from one that silently dropped them.
    grants: List[GrantIn] = []


class MemberAccessOut(Schema):
    user_id: str
    role: str
    # True: a server-wide role, which reaches every project. False: scoped to
    # `grants` only -- the same rule an invite follows.
    server_wide: bool
    grants: List[GrantIn] = []


class SetMemberAccessIn(Schema):
    """Full replace: no grants = server-wide at `role`; otherwise exactly these, at `role`."""
    role: str = "member"
    grants: List[GrantIn] = []


class MemberOut(Schema):
    user_id: str
    email: str
    role: str
    invited_by: Optional[str] = None
    joined_at: str
    avatar: Optional[str] = None  # #148


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
    email: Optional[str] = None        # human invite by email
    persona_name: Optional[str] = None  # persona invite by name (e.g. "Ryan" or "@Ryan")
    scope: str = "topic"
    topic_id: Optional[str] = None
    role: str = "member"
    redirect_to: Optional[str] = None   # see InviteRequest.redirect_to


class InviteToProjectOut(Schema):
    ok: bool
    is_new_user: bool
    email: str
    scope: str
    message: str
    server_url: Optional[str] = None
    invite_url: Optional[str] = None   # full link to share with the invitee
    email_sent: bool = False           # see InviteResponse.email_sent
    email_note: Optional[str] = None


class AvailableUserOut(Schema):
    user_id: str
    name: str
    email: str
    avatar: Optional[str] = None


class AvailablePersonaOut(Schema):
    persona_id: str
    user_id: str
    name: str
    avatar: Optional[str] = None
    # REMOVED: source_type -- the model/agent discriminator went away with
    # AIAgent. A persona's "agent-ness" is now emergent (does it have MCP
    # servers attached), and this picker does not need it.
