from ninja import Schema
from typing import Optional


class SendMessageIn(Schema):
    content: str


class MessageOut(Schema):
    id: str
    role: str           # "user" | "assistant"
    content: str
    status: str         # pending | streaming | completed | failed
    sender_name: Optional[str] = None
    sender_id: Optional[str] = None
    created_at: str


class SendMessageOut(Schema):
    user_message: MessageOut
    ai_message_id: str   # ID of the placeholder AI message — subscribe to this via Centrifugo
    channel: str         # Centrifugo channel to subscribe to: "topic:{topic_id}"
