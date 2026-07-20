from ninja import Schema
from typing import Optional


class SendMessageIn(Schema):
    content: str


class MessageOut(Schema):
    id: str
    type: str
    content: str
    sender_name: str
    sender_id: str
    sender_type: str
    sequence: int
    created_at: str


class SendMessageOut(Schema):
    message: MessageOut
    channel: str
