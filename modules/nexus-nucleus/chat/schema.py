from ninja import Schema
from typing import Optional


class SendMessageIn(Schema):
    content: str


class MessageOut(Schema):
    id: str
    type: str
    message_type: Optional[str] = None
    content: str
    sender_name: Optional[str] = None
    sender_id: Optional[str] = None
    sender_type: str
    sequence: int
    created_at: str


class SendMessageOut(Schema):
    message: MessageOut
    channel: str
