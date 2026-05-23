from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from .base import BaseModel, TenantBaseModel, ProjectBaseModel


class Invitation(TenantBaseModel):
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

    token_hash = models.CharField(max_length=255, unique=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    accepted_at = models.DateTimeField(null=True, blank=True)

    access_payload = models.JSONField(
        default=dict,
        blank=True,
        help_text="Project/topic access to grant after invitation is accepted.",
    )

    class Meta:
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

class Upload(TenantBaseModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        UPLOADING = "uploading", "Uploading"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"
        DELETED = "deleted", "Deleted"

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="uploads",
    )

    original_filename = models.CharField(max_length=255)
    mime_type = models.CharField(max_length=120, blank=True)
    file_size = models.BigIntegerField(default=0)

    file = models.FileField(
        upload_to="uploads/%Y/%m/%d/",
        null=True,
        blank=True,
    )

    storage_key = models.CharField(max_length=500, null=True, blank=True)

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )

    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "storage_upload"
        indexes = [
            models.Index(fields=["company", "status"]),
            models.Index(fields=["uploaded_by", "created_at"]),
        ]


class UploadPart(BaseModel):
    upload = models.ForeignKey(
        "nucleus.Upload",
        on_delete=models.CASCADE,
        related_name="parts",
    )

    part_number = models.PositiveIntegerField()
    etag = models.CharField(max_length=255, blank=True)
    size_bytes = models.BigIntegerField(default=0)
    storage_key = models.CharField(max_length=500, null=True, blank=True)

    class Meta:
        db_table = "storage_upload_part"
        constraints = [
            models.UniqueConstraint(
                fields=["upload", "part_number"],
                name="uniq_upload_part_number",
            )
        ]



class AgentRun(ProjectBaseModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        WAITING_APPROVAL = "waiting_approval", "Waiting Approval"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"

    agent = models.ForeignKey(
        "nucleus.AIAgent",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="runs",
    )

    topic = models.ForeignKey(
        "nucleus.ChatTopic",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="agent_runs",
    )

    triggered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="triggered_agent_runs",
    )

    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )

    input_payload = models.JSONField(default=dict, blank=True)
    output_payload = models.JSONField(default=dict, blank=True)

    error = models.TextField(null=True, blank=True)

    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "intelligence_agent_run"
        indexes = [
            models.Index(fields=["company", "project", "status"]),
            models.Index(fields=["agent", "created_at"]),
        ]



class KnowledgeChunk(BaseModel):
    knowledge_file = models.ForeignKey(
        "nucleus.KnowledgeFile",
        on_delete=models.CASCADE,
        related_name="chunks",
    )

    chunk_index = models.PositiveIntegerField()
    text = models.TextField()

    token_count = models.PositiveIntegerField(default=0)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "intelligence_knowledge_chunk"
        constraints = [
            models.UniqueConstraint(
                fields=["knowledge_file", "chunk_index"],
                name="uniq_knowledge_file_chunk_index",
            )
        ]


class EmbeddingJob(TenantBaseModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    target_type = models.CharField(max_length=50, db_index=True)
    target_id = models.UUIDField(db_index=True)

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )

    error = models.TextField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "intelligence_embedding_job"
        indexes = [
            models.Index(fields=["company", "status"]),
            models.Index(fields=["target_type", "target_id"]),
        ]


class VectorDocument(TenantBaseModel):
    source_type = models.CharField(max_length=50, db_index=True)
    source_id = models.UUIDField(db_index=True)

    vector_db = models.CharField(max_length=50, default="chroma")
    collection_name = models.CharField(max_length=255)
    vector_id = models.CharField(max_length=255)

    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "intelligence_vector_document"
        constraints = [
            models.UniqueConstraint(
                fields=["vector_db", "collection_name", "vector_id"],
                name="uniq_vector_document_external_id",
            )
        ]
        indexes = [
            models.Index(fields=["company", "source_type", "source_id"]),
        ]


class ProjectContext(ProjectBaseModel):
    class ContextType(models.TextChoices):
        KNOWLEDGE_BASE = "knowledge_base", "Knowledge Base"
        FILE = "file", "File"
        URL = "url", "URL"
        NOTE = "note", "Note"
        SYSTEM_INSTRUCTION = "system_instruction", "System Instruction"
        BUSINESS_RULE = "business_rule", "Business Rule"
        MCP_REFERENCE = "mcp_reference", "MCP Reference"

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
        db_table = "workspace_project_context"
        indexes = [
            models.Index(fields=["company", "project", "context_type"]),
        ]


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


class AuditEvent(TenantBaseModel):
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_events",
    )

    action = models.CharField(max_length=120, db_index=True)
    target_type = models.CharField(max_length=80, db_index=True)
    target_id = models.UUIDField(null=True, blank=True, db_index=True)

    payload = models.JSONField(default=dict, blank=True)

    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "governance_audit_event"
        indexes = [
            models.Index(fields=["company", "action"]),
            models.Index(fields=["target_type", "target_id"]),
            models.Index(fields=["created_at"]),
        ]


class Notification(TenantBaseModel):
    class NotificationType(models.TextChoices):
        INFO = "info", "Info"
        WARNING = "warning", "Warning"
        ERROR = "error", "Error"
        INVITATION = "invitation", "Invitation"
        AGENT = "agent", "Agent"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )

    notification_type = models.CharField(
        max_length=30,
        choices=NotificationType.choices,
        default=NotificationType.INFO,
    )

    title = models.CharField(max_length=255)
    body = models.TextField(blank=True)

    is_read = models.BooleanField(default=False, db_index=True)
    read_at = models.DateTimeField(null=True, blank=True)

    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "governance_notification"
        indexes = [
            models.Index(fields=["company", "user", "is_read"]),
            models.Index(fields=["created_at"]),
        ]


class UserSession(BaseModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="local_sessions",
    )

    provider = models.CharField(max_length=50, default="supabase")
    provider_session_id = models.CharField(max_length=255, null=True, blank=True)

    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(null=True, blank=True)

    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    is_current = models.BooleanField(default=True, db_index=True)

    class Meta:
        db_table = "accounts_user_session"
        indexes = [
            models.Index(fields=["user", "is_current"]),
        ]


class ModelUsageLog(TenantBaseModel):
    model = models.ForeignKey(
        "nucleus.AIModel",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="usage_logs",
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="model_usage_logs",
    )

    topic = models.ForeignKey(
        "nucleus.ChatTopic",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="model_usage_logs",
    )

    prompt_tokens = models.PositiveIntegerField(default=0)
    completion_tokens = models.PositiveIntegerField(default=0)
    total_tokens = models.PositiveIntegerField(default=0)

    latency_ms = models.PositiveIntegerField(default=0)
    cost_usd = models.DecimalField(max_digits=12, decimal_places=6, default=0)

    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "intelligence_model_usage_log"
        indexes = [
            models.Index(fields=["company", "model"]),
            models.Index(fields=["user", "created_at"]),
        ]


class AgentApproval(ProjectBaseModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        EXPIRED = "expired", "Expired"

    run = models.ForeignKey(
        "nucleus.AgentRun",
        on_delete=models.CASCADE,
        related_name="approvals",
    )

    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="requested_agent_approvals",
    )

    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_agent_approvals",
    )

    title = models.CharField(max_length=255)
    reason = models.TextField(blank=True)
    payload = models.JSONField(default=dict, blank=True)

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )

    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "intelligence_agent_approval"
        indexes = [
            models.Index(fields=["company", "project", "status"]),
        ]


class SavedSearch(TenantBaseModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="saved_searches",
    )

    name = models.CharField(max_length=255)
    query = models.TextField()
    filters = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "search_saved_search"
        constraints = [
            models.UniqueConstraint(
                fields=["company", "user", "name"],
                name="uniq_saved_search_name_per_user",
            )
        ]


class SearchLog(TenantBaseModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="search_logs",
    )

    query = models.TextField()
    search_type = models.CharField(max_length=50, db_index=True)
    filters = models.JSONField(default=dict, blank=True)

    result_count = models.PositiveIntegerField(default=0)
    latency_ms = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "search_log"
        indexes = [
            models.Index(fields=["company", "search_type"]),
            models.Index(fields=["user", "created_at"]),
        ]