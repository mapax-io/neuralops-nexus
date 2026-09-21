from ninja import Schema
from pydantic import field_validator
from typing import Optional


class SendMessageIn(Schema):
    content: str

    @field_validator("content")
    @classmethod
    def validate_content(cls, v: str) -> str:
        """
        Strips and validates once, here, instead of chat/api.py:send_message
        doing an empty-check, MessageDirectives(...), and _save_user_message(...)
        each independently calling .strip() on the same raw string. Whatever
        comes out of this schema is already the value everything downstream uses.
        """
        v = v.strip()
        if not v:
            raise ValueError("Message content cannot be empty.")
        if len(v) > 4000:
            raise ValueError("Message too long (max 4000 characters). Attach large text as a context source.")
        return v


class MessageOut(Schema):
    id: str
    type: str
    message_type: Optional[str] = None
    content: str
    render_as: str = "text"       # M7: "text" | "code" | "html" | "terminal" | "chart"
    output_type: str = "text"     # M7: "text" | "chart" | "code" | "table" | ...
    stopped: bool = False         # the reader ended the reply; content is what streamed
    status: str = "completed"     # pending | completed | failed — a failed reply's content is its reason
    # Team AI operations (additive; the app feature-detects each):
    activity_trail: list = []                 # [{tool, ok, duration_ms, preview}] — what the persona did
    preflight: Optional[dict] = None          # a proposed run awaiting a decision, and the decision
    answered_by_model: Optional[str] = None   # set when a fallback model answered
    usage: Optional[dict] = None              # {prompt_tokens, output_tokens, context_window} from the worker
    sender_name: Optional[str] = None
    sender_id: Optional[str] = None
    sender_avatar: Optional[str] = None  # #148 -- absolute URL, or None
    sender_type: str
    persona_id: Optional[str] = None  # frozen at send-time -- distinguishes two
                                       # personas that have shared the same name
                                       # over time (e.g. deleted + recreated "Nova")
    sequence: int
    created_at: str


class MentionRefusalOut(Schema):
    """A persona in the sender's message that will not answer, and why."""
    persona_id: str
    name: str
    code: str                       # "no_right" today; per-persona codes arrive with call rights
    message: str
    resets_at: Optional[str] = None  # set once limits exist


class SendMessageOut(Schema):
    message: MessageOut
    channel: str
    # Only the AI reply is withheld -- the message above always posted.
    refusals: list[MentionRefusalOut] = []


class StopMessageOut(Schema):
    stopping: bool
