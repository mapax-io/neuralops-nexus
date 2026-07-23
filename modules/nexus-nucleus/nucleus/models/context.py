"""
ContextSource — a file or web URL attached to a ChatTopic as context.

When a source is attached:
  nucleus stores the record (status=pending)
  nucleus extracts content and calls nexus-ai /embed/
  nexus-ai returns collection_id → stored back here (status=ready)

When a source is detached:
  nucleus calls nexus-ai DELETE /embed/context-source/{collection_id}/
  nucleus deletes the record
"""
from django.db import models

from .base import TenantBaseModel


class ContextSource(TenantBaseModel):

    class Type(models.TextChoices):
        FILE = "file", "File"
        WEB  = "web",  "Web URL"

    class Status(models.TextChoices):
        PENDING   = "pending",   "Pending"
        READY     = "ready",     "Ready"
        ERROR     = "error",     "Error"

    topic = models.ForeignKey(
        "nucleus.ChatTopic",
        on_delete=models.CASCADE,
        related_name="context_sources",
    )

    type  = models.CharField(max_length=10, choices=Type.choices)
    name  = models.CharField(max_length=255)

    # File source
    file          = models.FileField(upload_to="context_sources/%Y/%m/%d/", null=True, blank=True)
    file_size     = models.BigIntegerField(default=0)
    mime_type     = models.CharField(max_length=100, blank=True)

    # Web source
    url = models.URLField(null=True, blank=True)

    # SHA-256 of file content — used to skip re-embedding identical files
    checksum      = models.CharField(max_length=64, blank=True, db_index=True)

    # Set by nexus-ai after embedding
    collection_id = models.CharField(max_length=255, blank=True)
    status        = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True)
    error         = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "context_source"
        indexes = [
            models.Index(fields=["topic", "type"]),
            models.Index(fields=["company", "topic"]),
            models.Index(fields=["topic", "checksum"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.type}) — {self.topic}"
