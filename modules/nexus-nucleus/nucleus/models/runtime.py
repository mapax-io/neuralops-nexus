"""
Run-time state — the parked runs (Step 2 of the nucleus revamp,
docs/NUCLEUS-REVAMP.md).

PausedRun: one row per reply the engine paused mid-run for a person
(a tool approval or a question — engine item 2 / item 5). The engine POSTs
this to /api/v1/internal/messages/{msg_id}/pause/ BEFORE it ends the stream
with message_paused, so a decision can never race an unsaved state. The
relay then adds the ORIGINAL trigger job to the row; a resume re-sends that
job plus the decisions, and the row is consumed.

The state JSON (the run's full model messages) can be large and must never
ride to the browser — that is why this is its own table and not message
metadata.
"""
import uuid

from django.db import models


class PausedRun(models.Model):
    """One paused reply: everything a resume needs."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # The reply message this run belongs to — one pause at a time per reply.
    message_id = models.CharField(max_length=64, unique=True, db_index=True)
    job_id = models.CharField(max_length=128, blank=True, default="")
    topic_id = models.CharField(max_length=64, db_index=True)
    persona_id = models.CharField(max_length=64, blank=True, default="")

    # From the engine's pause POST:
    state = models.TextField()  # ModelMessages JSON, resent verbatim in resume.state
    catalog_hash = models.CharField(max_length=128, blank=True, default="")
    pending = models.JSONField(default=list)  # [{call_id, tool, capability_id, args_preview, kind}]
    role = models.CharField(max_length=20, blank=True, default="STANDARD")  # the model seat (item 13)

    # Added by the relay on message_paused: the original trigger job, so the
    # resume re-sends the same fields. Empty = nucleus restarted in between;
    # that run cannot be resumed (the decision road fails it politely).
    job = models.JSONField(default=dict, blank=True)

    # {call_id: {kind: approval|question, decision/answer, decided_by_id,
    #  decided_by_name, decided_at, reason?}} — the resume fires when every
    # pending call_id has an entry here (the engine needs a result per call).
    decisions = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "chat_paused_run"

    def __str__(self) -> str:
        return f"paused {self.message_id} ({len(self.pending or [])} pending)"
