"""Schemas for the /embed/ endpoints (nexus-nucleus → nexus-ai)."""
from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Context-source embedding (documents / code files)
# ---------------------------------------------------------------------------

class EmbedRequest(BaseModel):
    source_id: str                   # ContextSource UUID from nexus-nucleus
    type: str                        # "doc" | "code"
    label: str                       # human-readable name ("auth.py")
    content: str                     # raw file content
    language: str | None = None      # code only ("python", "typescript", etc.)


class EmbedResponse(BaseModel):
    source_id: str
    collection_id: str               # Chroma collection ID — stored back in nexus-nucleus
    chunks_count: int


# ---------------------------------------------------------------------------
# Chat message embedding (M2)
# ---------------------------------------------------------------------------

class MessageEmbedRequest(BaseModel):
    message_id: str                  # ChatMessage UUID
    company_id: str                  # Tenant scope → collection company_{company_id}_chat
    sequence: int                    # Message sequence number within the topic
    topic_id: str
    channel_id: str
    project_id: str
    sender_id: str
    sender_name: str
    sender_type: str                 # "human" | "persona"
    content: str                     # Message text to embed
    created_at: str                  # ISO-8601 timestamp


class MessageEmbedResponse(BaseModel):
    message_id: str
    collection: str                  # ChromaDB collection name used
    embedding_model: str             # Model name stored in metadata (for change detection)
    ok: bool
