"""
The money tables — Step 1 of the nucleus revamp (docs/NUCLEUS-REVAMP.md;
engine contract: docs/NUCLEUS-HANDOFF.md change 1).

UsageRecord: one row per model call, exactly as nexus-ai reports it on
POST /api/v1/internal/usage/ — tokens with full cache detail, which
persona/model/seat ran, what KIND of call it was (chat_reply / router /
memory / remote_embedder), when. Cost is computed AT INSERT (intelligence/
pricing.py) as an exact Decimal and stored frozen — recomputing later from
current prices would silently rewrite historical spend.

Deliberately NO foreign keys (Step 1 design note): billing records must
survive any deletion of what they bill, and the engine's delegation rows use
composite message ids ("<msg>:cp0") that have no row to point at. Plain
indexed id columns instead.

ModelPrice: the local price catalog, refreshed from an online source by a
periodic task (intelligence/tasks.py). Owner's ruling: prices are always
presented as ESTIMATED — "prices not confirmed" — and an admin-typed override
on the ModelConfig row beats the catalog.

Retention (owner's ruling): keep every row, no pruning in v1.
"""
import uuid

from django.db import models


class ModelPrice(models.Model):
    """One catalog row: what a (provider, model) costs per million tokens.
    Written by the refresh task; read by intelligence/pricing.py. Prices are
    USD per MILLION tokens, Decimal — never float."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    provider = models.CharField(max_length=50, db_index=True)
    model_id = models.CharField(max_length=255, db_index=True)

    input_per_million = models.DecimalField(max_digits=12, decimal_places=6, null=True, blank=True)
    cached_per_million = models.DecimalField(max_digits=12, decimal_places=6, null=True, blank=True)
    output_per_million = models.DecimalField(max_digits=12, decimal_places=6, null=True, blank=True)

    # Catalog-known SIZES (owner's ruling 2026-10-21: the register dialog's
    # defaults come from a DB the refresh task updates, not a hardcoded
    # table). Null = the source doesn't say; the dialog then falls back to
    # its built-in offline guesses. Served by GET /model-configs/defaults/.
    context_window = models.PositiveIntegerField(null=True, blank=True)
    max_output_tokens = models.PositiveIntegerField(null=True, blank=True)

    source = models.CharField(
        max_length=100, default="catalog",
        help_text="Where this row came from, e.g. the online catalog's name.",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "usage_model_price"
        constraints = [
            models.UniqueConstraint(fields=["provider", "model_id"],
                                    name="uniq_price_per_provider_model"),
        ]

    def __str__(self) -> str:
        return f"{self.provider}:{self.model_id}"


class UsageRecord(models.Model):
    """One model call, as the engine reported it. Field names and meanings
    mirror the engine's UsageRecord dataclass byte for byte (its tests T4/T5
    define the arithmetic): input_tokens INCLUDES cache read + write;
    output_tokens INCLUDES reasoning."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # who / where — ids as plain text on purpose (see module docstring)
    company_id = models.CharField(max_length=64, db_index=True)
    project_id = models.CharField(max_length=64, db_index=True)
    topic_id = models.CharField(max_length=64, db_index=True)
    persona_id = models.CharField(max_length=64, db_index=True)
    user_id = models.CharField(max_length=64, blank=True, default="")
    message_id = models.CharField(max_length=128, db_index=True)  # may be "<msg>:cp0"
    job_id = models.CharField(max_length=128, blank=True, default="")

    # what
    kind = models.CharField(max_length=32, db_index=True)  # chat_reply|router|memory|remote_embedder
    model_config_id = models.CharField(max_length=64, blank=True, default="")
    provider = models.CharField(max_length=50)
    model_id = models.CharField(max_length=255)
    role = models.CharField(max_length=20, blank=True, default="")  # the seat (STANDARD/ROUTER/…)
    provider_response_id = models.CharField(max_length=255, null=True, blank=True)
    source = models.CharField(max_length=50, null=True, blank=True)  # e.g. "router_failed"

    # counts (engine semantics: totals include the cache/reasoning parts)
    input_tokens = models.BigIntegerField(default=0)
    uncached_input_tokens = models.BigIntegerField(default=0)
    cache_read_tokens = models.BigIntegerField(default=0)
    cache_write_5m_tokens = models.BigIntegerField(default=0)
    cache_write_1h_tokens = models.BigIntegerField(default=0)
    output_tokens = models.BigIntegerField(default=0)
    reasoning_tokens = models.BigIntegerField(default=0)
    finish_reason = models.CharField(max_length=50, null=True, blank=True)
    estimated = models.BooleanField(default=False)  # the COUNTS are estimated (cut stream)

    # money — frozen at insert; always presented as estimated (owner's ruling)
    cost = models.DecimalField(max_digits=14, decimal_places=8, null=True, blank=True)
    prices_used = models.JSONField(null=True, blank=True)  # the per-million numbers applied
    price_source = models.CharField(
        max_length=20, blank=True, default="",
        help_text="override (admin-typed) | catalog | '' (no price known — cost null)",
    )

    called_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "usage_record"
        indexes = [
            models.Index(fields=["company_id", "created_at"], name="usage_rec_company_created_idx"),
            models.Index(fields=["project_id", "created_at"], name="usage_rec_project_created_idx"),
            models.Index(fields=["topic_id", "created_at"], name="usage_rec_topic_created_idx"),
            models.Index(fields=["persona_id", "created_at"], name="usage_rec_persona_created_idx"),
            models.Index(fields=["company_id", "kind"], name="usage_rec_company_kind_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.kind} {self.model_id} in={self.input_tokens} out={self.output_tokens}"
