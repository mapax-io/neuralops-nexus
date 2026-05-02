# apps/core/models.py

import uuid
from django.db import models


class UUIDModel(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    class Meta:
        abstract = True


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
    )
    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        abstract = True


class SoftDeleteModel(models.Model):
    is_active = models.BooleanField(default=True, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        abstract = True


class BaseModel(UUIDModel, TimeStampedModel, SoftDeleteModel):
    """
    Common base model for almost all tables.
    """

    class Meta:
        abstract = True



class TenantBaseModel(BaseModel):

    """

    Base model for company-owned records.

    Example: Project, Agent, AIModel, MCPServer, KnowledgeBase.

    """

    company = models.ForeignKey(

        "governance.Company",

        on_delete=models.CASCADE,

        related_name="%(class)s_items",

        db_index=True,

    )

    class Meta:

        abstract = True

class ProjectBaseModel(TenantBaseModel):
    """
    Base model for project-owned records.
    Example: Channel, ChatTopic, ChatLine, Persona.
    """

    project = models.ForeignKey(
        "workspace.Project",
        on_delete=models.CASCADE,
        related_name="%(class)s_items",
        db_index=True,
    )

    class Meta:
        abstract = True