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

    # Step 3 (handoff change 10): the project's embedder spec
    # {provider: fastembed|openai_compatible|hash, model_id, api_base?,
    # api_key?}. Null = the system default (local fastembed). Changing it
    # rebuilds the project's vectors — see the reindex flow.
    embedder = models.JSONField(null=True, blank=True)
    # "" | "building" | "failed" — while "building", persona triggers in
    # this project are refused with a worded message (the index is being
    # rebuilt; the old one stays active underneath, so a crash is safe).
    reindex_status = models.CharField(max_length=10, blank=True, default="")

    # DEFAULT ROUTER — ruled PROJECT-wide (owner, 2026-10-19 23:43: "models
    # can be company wide, but it will be used as project persona router").
    # Fills a persona's EMPTY router seat at serve time (internal/api.py);
    # a persona's own seat always wins, and a default equal to a persona's
    # standard model is skipped for that persona (screening with the same
    # model saves nothing). The dormant CompanyAIConfig.default_router_model
    # column is NOT read any more.
    default_router_model = models.ForeignKey(
        "nucleus.ModelConfig", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
        help_text="Fills the router seat of this project's personas that have none of their own.",
    )

    # SPEND LIMIT (owner's ruling 2026-10-21: per-project monthly cap, BLOCK
    # when reached). USD per calendar month, compared against the sum of this
    # project's UsageRecord.cost — which is ESTIMATED by design (prices not
    # confirmed; unpriced rows count as 0). Null = no limit. Enforced where
    # persona triggers fire (chat/api.py _trigger_personas, same road as the
    # reindex lock); the human message still posts — only the AI reply is
    # withheld, with a worded refusal.
    spend_limit_monthly = models.DecimalField(
        max_digits=9, decimal_places=2, null=True, blank=True,
        help_text="USD per calendar month; personas here stop answering once the month's estimated spend reaches it.",
    )

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
    ChatReadMarker, and context sources (ContextSource) all
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

    # Step 6 (docs/NUCLEUS-REVAMP.md, change 13.3): the project's reserved
    # "configure" topic — where the provisioning persona lives. Visible to
    # exactly the four admin-tier roles (the project.update holders); the
    # fence is enforced in authn/permissions/row_rules.py, so every road
    # (lists, messages, search, the gateway) honours it from one place.
    is_configure = models.BooleanField(default=False, db_index=True)

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
# REMOVED (owner's ruling 2026-10-22, "remove every install from front or
# backend"): Deliverable (W10) — the keep-a-reply feature. Dropped with
# migration 0042 alongside RecallEntry.


class ChatMessage(ProjectBaseModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        STREAMING = "streaming", "Streaming"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"
        # Step 2: parked mid-run, waiting on a person (approval or question);
        # resumed through chat/relay.py with the stored PausedRun state.
        PAUSED = "paused", "Paused"

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

# Step 0 (NUCLEUS-REVAMP.md, 2026-10-14): KnowledgeBase, KnowledgeFile, ChatReaction and ChatAttachment removed -- zero code references outside their definitions (migration 0029 drops the tables).
