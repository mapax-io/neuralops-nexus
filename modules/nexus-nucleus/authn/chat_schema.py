from ninja import Schema
from typing import Optional


class SendMessageIn(Schema):
    content: str


class MessageOut(Schema):
    id: str
    type: str           # "message" | "token" | "done" — Phase 1 always "message"
    content: str
    sender_name: str
    sender_id: str
    created_at: str


class SendMessageOut(Schema):
    message: MessageOut
    channel: str        # Centrifugo channel to subscribe to: "topic:{topic_id}"
