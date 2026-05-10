# apps/core/models.py

import uuid
import uuid

from django.db import models

from django.utils import timezone


class UUIDModel(models.Model):
    """

    Abstract base model that provides a UUID primary key.

    This class can be inherited by other Django models to replace the default

    auto-incrementing integer primary key (`id`) with a universally unique

    identifier (UUID).

    Why use UUIDs?

    - Better for distributed systems (no collision across databases)

    - Safer to expose in APIs (harder to guess than integers)

    - Useful for multi-tenant and external integrations

    Usage:

        class MyModel(UUIDModel):

            name = models.CharField(max_length=100)

    This will automatically add a UUID `id` field as the primary key.

    """
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    class Meta:
        abstract = True


class TimeStampedModel(models.Model):
    """
    Abstract base model that provides created and updated timestamps.

    This class can be inherited by other Django models to automatically
    add `created_at` and `updated_at` fields, which are useful for tracking
    the creation and modification times of records.

    Usage:

        class MyModel(TimeStampedModel):
            name = models.CharField(max_length=100)

    This will automatically add `created_at` and `updated_at` fields.
    """
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

    """

    Abstract base model that supports soft deletion.

    """

    is_active = models.BooleanField(default=True, db_index=True)

    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:

        abstract = True

    def soft_delete(self, save=True):

        self.is_active = False

        self.deleted_at = timezone.now()

        if save:

            self.save(update_fields=["is_active", "deleted_at", "updated_at"])

    def restore(self, save=True):

        self.is_active = True

        self.deleted_at = None

        if save:

            self.save(update_fields=["is_active", "deleted_at", "updated_at"])




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

        "nucleus.Company",

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
        "nucleus.Project",
        on_delete=models.CASCADE,
        related_name="%(class)s_items",
        db_index=True,
    )

    class Meta:
        abstract = True