from django.conf import settings
from django.db import models
from .base import BaseModel, TenantBaseModel, ProjectBaseModel, TenantOperationModel


class Invitation(TenantOperationModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACCEPTED = "accepted", "Accepted"
        REVOKED = "revoked", "Revoked"
        EXPIRED = "expired", "Expired"

    email = models.EmailField(db_index=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )

    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sent_invitations",
    )

    role = models.CharField(
        max_length=20,
        default="member",
        db_index=True,
        help_text="CompanyAccess role to assign when invitation is accepted.",
    )

    token_hash = models.CharField(max_length=255, unique=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    accepted_at = models.DateTimeField(null=True, blank=True)

    access_payload = models.JSONField(
        default=dict,
        blank=True,
        help_text="Project/topic access to grant after invitation is accepted.",
    )

    class Meta(TenantOperationModel.Meta):
        db_table = "governance_invitation"
        indexes = [
            models.Index(fields=["company", "email"]),
            models.Index(fields=["company", "status"]),
        ]


class ProjectMember(ProjectBaseModel):
    class Role(models.TextChoices):
        OWNER = "owner", "Owner"
        ADMIN = "admin", "Admin"
        MEMBER = "member", "Member"
        VIEWER = "viewer", "Viewer"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="project_memberships",
    )

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.MEMBER,
        db_index=True,
    )

    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "workspace_project_member"
        constraints = [
            models.UniqueConstraint(
                fields=["project", "user"],
                name="uniq_project_user_member",
            )
        ]
        indexes = [
            models.Index(fields=["company", "project"]),
            models.Index(fields=["user", "is_active"]),
        ]


class TopicParticipant(ProjectBaseModel):
    class Role(models.TextChoices):
        OWNER = "owner", "Owner"
        MODERATOR = "moderator", "Moderator"
        PARTICIPANT = "participant", "Participant"
        OBSERVER = "observer", "Observer"

    topic = models.ForeignKey(
        "nucleus.ChatTopic",
        on_delete=models.CASCADE,
        related_name="participants",
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="topic_participations",
    )

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.PARTICIPANT,
        db_index=True,
    )

    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "workspace_topic_participant"

        constraints = [
            models.UniqueConstraint(
                fields=["topic", "user"],
                name="uniq_topic_user_participant",
            )
        ]

        indexes = [
            models.Index(fields=["company", "project", "topic"]),
            models.Index(fields=["user", "is_active"]),
            models.Index(fields=["role"]),
        ]

    def __str__(self):
        return f"{self.user} in {self.topic} ({self.role})"


class TopicContext(ProjectBaseModel):
    class ContextType(models.TextChoices):
        KNOWLEDGE_BASE = "knowledge_base", "Knowledge Base"
        FILE = "file", "File"
        UPLOAD = "upload", "Upload"
        NOTE = "note", "Note"
        MESSAGE = "message", "Message"
        SYSTEM_INSTRUCTION = "system_instruction", "System Instruction"

    topic = models.ForeignKey(
        "nucleus.ChatTopic",
        on_delete=models.CASCADE,
        related_name="contexts",
    )

    context_type = models.CharField(
        max_length=50,
        choices=ContextType.choices,
        db_index=True,
    )

    title = models.CharField(max_length=255)
    content = models.TextField(blank=True)

    reference_id = models.UUIDField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "workspace_topic_context"
        indexes = [
            models.Index(fields=["company", "project", "topic"]),
            models.Index(fields=["context_type"]),
        ]

# class AgentRun(ProjectBaseModel)        -- dropped in migration 0007
# class AgentApproval(ProjectBaseModel)   -- dropped in migration 0006
# class ModelUsageLog(TenantBaseModel)    -- dropped in migration 0008

# Step 0 (NUCLEUS-REVAMP.md, 2026-10-14): Upload, UploadPart, KnowledgeChunk, EmbeddingJob, VectorDocument, ProjectContext, AuditEvent, Notification, UserSession, SavedSearch and SearchLog removed -- zero code references outside their definitions (migration 0029 drops the tables). TopicContext, Invitation, ProjectMember and TopicParticipant are alive and stay.
