"""Schemas for the /embed/ endpoint (nexus-nucleus → nexus-ai)."""
from pydantic import BaseModel


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
