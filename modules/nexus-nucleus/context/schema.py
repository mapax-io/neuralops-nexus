from typing import Optional
from ninja import Schema, Field


class ContextSourceOut(Schema):
    id: str
    topic_id: str
    type: str
    name: str
    url: Optional[str] = None
    collection_id: str
    status: str
    error: Optional[str] = None
    created_at: str


class ContextSourceWebIn(Schema):
    url: str
    name: Optional[str] = None   # defaults to URL if not provided


# ── Context Panel (M6) ───────────────────────────────────────────────────────

class PanelDeleteItemIn(Schema):
    """One item to remove — directive identifies the provider, id is the item's PK."""
    directive: str
    id: str


class PanelDeleteIn(Schema):
    """Payload for DELETE /context-panel/items/"""
    items: list[PanelDeleteItemIn]
