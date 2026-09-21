from django.conf import settings

from django.db import models

from .base import TenantBaseModel, ProjectBaseModel, BaseModel, TenantOperationModel, ProjectOperationModel

class Project(TenantOperationModel):
    """
    Top-level container within a company (tenant).

    A Project is the root of the workspace hierarchy: Company -> Project ->
    Channel -> ChatTopic. Everything a team works on -- channels, topics,
    AI agents/personas, context sources -- is scoped under a Project.

    Membership is managed through ProjectMember (see below), which also
    carries each member's role (owner/admin/member/viewer).
    """
    name = models.CharField(max_length=255)
    slug = models.SlugField(
        max_length=120,
        help_text="URL-safe identifier, unique per company. Auto-generated from name.",
    )
    description = models.TextField(blank=True, null=True)
    # Project Brief: always-on instructions every persona turn in this project
    # honours (the worker puts it ahead of the persona's own prompt). Plain
    # text/markdown, capped in workspace/services.py, empty = none.
    brief = models.TextField(blank=True, default="")
    brief_updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
    )
    brief_updated_at = models.DateTimeField(null=True, blank=True)

    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        through="ProjectMember",
        through_fields=("project", "user"),
        related_name="member_projects",
        blank=True,
        help_text="Users with access to this project. Role/status tracked on ProjectMember.",
    )

    class Meta(TenantOperationModel.Meta):
        db_table = "workspace_project"
        constraints = [
            models.UniqueConstraint(
                fields=["company", "slug"],
                name="uniq_project_slug_per_company",
            )
        ]

    def __str__(self):
        return f"{self.company.name} / {self.name}"

class Channel(ProjectOperationModel):
    """
    A named subdivision of a Project used to organize related discussion.

    Channels group ChatTopics by subject area (e.g. "Backend", "Design").
    Every message ultimately lives under Company -> Project -> Channel ->
    ChatTopic -> ChatMessage.
    """
    name = models.CharField(max_length=255)
    slug = models.SlugField(
        max_length=120,
        help_text="URL-safe identifier, unique per project. Auto-generated from name.",
    )
    description = models.TextField(blank=True, null=True)

    class Meta(ProjectOperationModel.Meta):
        db_table = "workspace_channel"
        constraints = [
            models.UniqueConstraint(
                fields=["project", "slug"],
                name="uniq_channel_slug_per_project",
            )
        ]
        indexes = [
            models.Index(fields=["company", "project"]),
        ]

    def __str__(self):
        return f"{self.project.name} / {self.name}"

class ChatTopic(ProjectOperationModel):
    """
    A single conversation thread within a Channel.

    This is the unit chat actually happens in -- ChatMessage, ChatSession,
    ChatReadMarker, and context sources (ContextSource/KnowledgeBase) all
    attach to a ChatTopic, not to the Channel or Project directly.
    """
    channel = models.ForeignKey(
        "nucleus.Channel",
        on_delete=models.CASCADE,
        related_name="topics",
    )

    title = models.CharField(max_length=255)
    slug = models.SlugField(
        max_length=120,
        help_text="URL-safe identifier, unique per channel. Auto-generated from title.",
    )

    class Meta(ProjectOperationModel.Meta):
        db_table = "workspace_chat_topic"
        constraints = [
            models.UniqueConstraint(
                fields=["channel", "slug"],
                name="uniq_topic_slug_per_channel",
            )
        ]
        indexes = [
            models.Index(fields=["company", "project", "channel"]),
        ]

    def __str__(self):
        return f"{self.channel.name} / {self.title}"

class KnowledgeBase(TenantBaseModel):
    """
    Company-owned knowledge base.

    One knowledge base can be attached to projects, channels,
    and chat topics.
    """

    name = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True)

    projects = models.ManyToManyField(
        "nucleus.Project",
        related_name="knowledge_bases",
        blank=True,
    )

    # channels = models.ManyToManyField(
    #     "nucleus.Channel",
    #     related_name="knowledge_bases",
    #     blank=True,
    # )

    chat_topics = models.ManyToManyField(
        "nucleus.ChatTopic",
        related_name="knowledge_bases",
        blank=True,
    )

    class Meta:
        db_table = "intelligence_knowledge_base"
        constraints = [
            models.UniqueConstraint(
                fields=["company", "name"],
                name="uniq_knowledge_base_name_per_company",
            )
        ]
        indexes = [
            models.Index(fields=["company", "is_active"]),
        ]

    def __str__(self):
        return self.name
    
class KnowledgeFile(BaseModel):
    knowledge_base = models.ForeignKey(
        "nucleus.KnowledgeBase",
        on_delete=models.CASCADE,
        related_name="files",
    )

    file = models.FileField(upload_to="knowledge_files/%Y/%m/%d/")
    original_filename = models.CharField(max_length=255)
    mime_type = models.CharField(max_length=100, blank=True)
    file_size = models.BigIntegerField(default=0)

    chroma_collection = models.CharField(max_length=255, null=True, blank=True)
    embedding_status = models.CharField(max_length=30, default="pending")

    class Meta:
        db_table = "intelligence_knowledge_file"

class Deliverable(ProjectBaseModel):
    """
    Something a persona produced that the team decided to keep (W10): a chart, a
    page, a table, a form. A reply scrolls away; a deliverable does not.

    Kept by title, versioned: keeping the same title again adds a version rather
    than overwriting, so a number that was signed off last week is still there
    next to the one that replaced it. The source message is remembered when it
    is still around, and forgotten (SET_NULL) rather than taking the deliverable
    with it.
    """

    class Kind(models.TextChoices):
        HTML = "html", "Page"
        CHART = "chart", "Chart"
        TABLE = "table", "Table"
        FORM = "form", "Form"
        TEXT = "text", "Text"

    title = models.CharField(max_length=120)
    kind = models.CharField(max_length=12, choices=Kind.choices, default=Kind.TEXT)
    version = models.PositiveIntegerField(default=1)
    content = models.TextField(help_text="Exactly what the reply carried -- the chart's JSON, the page's HTML.")
    source_message = models.ForeignKey(
        "nucleus.ChatMessage", on_delete=models.SET_NULL, null=True, blank=True, related_name="deliverables",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="kept_deliverables",
    )

    class Meta:
        ordering = ["title", "-version"]
        indexes = [models.Index(fields=["project", "is_active"])]
        constraints = [
            models.UniqueConstraint(
                fields=["project", "title", "version"],
                condition=models.Q(is_active=True),
                name="one_version_per_title_per_project",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.title} v{self.version}"


class ChatMessage(ProjectBaseModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        STREAMING = "streaming", "Streaming"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"

    class MessageType(models.TextChoices):
        TEXT = "text", "Text"
        MARKDOWN = "markdown", "Markdown"
        CODE = "code", "Code"
        GRAPH = "graph", "Graph"
        FORM = "form", "Form"
        IMAGE = "image", "Image"
        FILE = "file", "File"
        AUDIO = "audio", "Audio"
        VIDEO = "video", "Video"
        SYSTEM = "system", "System"
        MIXED = "mixed", "Mixed"

    topic = models.ForeignKey(
        "nucleus.ChatTopic",
        on_delete=models.CASCADE,
        related_name="messages",
    )

    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="chat_messages",
    )

    message_type = models.CharField(
        max_length=20,
        choices=MessageType.choices,
        default=MessageType.TEXT,
        db_index=True,
    )

    content = models.TextField(blank=True)

    content_json = models.JSONField(
        default=dict,
        blank=True,
        help_text="Forms, graphs, tool outputs, structured AI response, etc.",
    )

    language = models.CharField(
        max_length=20,
        null=True,
        blank=True,
        help_text="Example: en, ur, ar, fr, python, javascript",
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.COMPLETED,
        db_index=True,
    )

    parent = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="replies",
    )
    retry_of = models.ForeignKey(

        "self",

        on_delete=models.SET_NULL,

        null=True,

        blank=True,

        related_name="retries",

    )

    sequence = models.PositiveIntegerField(default=0)

    is_deleted_from_context = models.BooleanField(default=False)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "workspace_chat_message"
        indexes = [
            models.Index(fields=["company", "project", "topic"]),
            models.Index(fields=["topic", "created_at"]),
            models.Index(fields=["sender", "created_at"]),
            models.Index(fields=["message_type"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return f"{self.sender}: {self.content[:50]}"

class ChatReadMarker(BaseModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="chat_read_markers",
    )

    topic = models.ForeignKey(
        "nucleus.ChatTopic",
        on_delete=models.CASCADE,
        related_name="read_markers",
    )

    last_read_message = models.ForeignKey(
        "nucleus.ChatMessage",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        db_table = "workspace_chat_read_marker"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "topic"],
                name="uniq_user_topic_read_marker",
            )
        ]
        indexes = [
            models.Index(fields=["user", "topic"]),
        ]

class ChatReaction(BaseModel):
    message = models.ForeignKey(
        "nucleus.ChatMessage",
        on_delete=models.CASCADE,
        related_name="reactions",
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="chat_reactions",
    )

    emoji = models.CharField(max_length=20)

    class Meta:
        db_table = "workspace_chat_reaction"
        constraints = [
            models.UniqueConstraint(
                fields=["message", "user", "emoji"],
                name="uniq_message_user_emoji_reaction",
            )
        ]
        indexes = [
            models.Index(fields=["message", "emoji"]),
            models.Index(fields=["user"]),
        ]

class ChatSession(BaseModel):
    """
    Per-user, per-topic AI session.

    Created when a user fires @session — allows subsequent plain messages
    to trigger the active personas automatically (no re-mention needed).
    Timer is fixed from session open time, not rolling.
    UniqueConstraint(user, topic) — one active session per user per topic.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="chat_sessions",
    )

    topic = models.ForeignKey(
        "nucleus.ChatTopic",
        on_delete=models.CASCADE,
        related_name="chat_sessions",
    )

    personas = models.ManyToManyField(
        "nucleus.Persona",
        related_name="chat_sessions",
        blank=True,
    )

    expires_at = models.DateTimeField(
        help_text="Fixed expiry from session open time. Not rolling.",
    )

    class Meta:
        db_table = "workspace_chat_session"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "topic"],
                name="uniq_user_topic_chat_session",
            )
        ]
        indexes = [
            models.Index(fields=["user", "topic"]),
            models.Index(fields=["expires_at"]),
        ]

    def __str__(self):
        return f"Session({self.user}, {self.topic})"

class ChatAttachment(BaseModel):
    class AttachmentType(models.TextChoices):
        IMAGE = "image", "Image"
        PDF = "pdf", "PDF"
        DOCUMENT = "document", "Document"
        AUDIO = "audio", "Audio"
        VIDEO = "video", "Video"
        CSV = "csv", "CSV"
        JSON = "json", "JSON"
        OTHER = "other", "Other"

    message = models.ForeignKey(
        "nucleus.ChatMessage",
        on_delete=models.CASCADE,
        related_name="attachments",
    )

    attachment_type = models.CharField(
        max_length=20,
        choices=AttachmentType.choices,
        default=AttachmentType.OTHER,
    )

    file = models.FileField(upload_to="chat_attachments/%Y/%m/%d/")
    original_filename = models.CharField(max_length=255)
    mime_type = models.CharField(max_length=100, blank=True)
    file_size = models.BigIntegerField(default=0)

    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "workspace_chat_attachment"
        indexes = [
            models.Index(fields=["message"]),
            models.Index(fields=["attachment_type"]),
        ]
