from typing import Optional, List
from ninja import Schema


# ── Projects ──────────────────────────────────────────────────────────────────

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


# ── Channels ──────────────────────────────────────────────────────────────────

class ChannelCreateRequest(Schema):
    name: str
    description: Optional[str] = None


# ── Topics ────────────────────────────────────────────────────────────────────

class TopicCreateRequest(Schema):
    title: str


class TopicOut(Schema):
    id: str
    title: str
    slug: str
    channel_id: str
    project_id: str
