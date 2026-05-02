from django.conf import settings

from django.db import models

from .base import TenantBaseModel, ProjectBaseModel, BaseModel

class Project(TenantBaseModel):

    name = models.CharField(max_length=255)

    slug = models.SlugField(max_length=120)

    description = models.TextField(blank=True, null=True)

    class Meta:

        db_table = "workspace_project"

        constraints = [

            models.UniqueConstraint(

                fields=["company", "slug"],

                name="uniq_project_slug_per_company",

            )

        ]

    def __str__(self):

        return f"{self.company.name} / {self.name}"

class ChatTopic(ProjectBaseModel):

    title = models.CharField(max_length=255)

    slug = models.SlugField(max_length=120)

    class Meta:

        db_table = "workspace_chat_topic"

        constraints = [

            models.UniqueConstraint(

                fields=["project", "slug"],

                name="uniq_topic_slug_per_project",

            )

        ]

    def __str__(self):

        return f"{self.project.name} / {self.title}"
    
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
        ChatTopic,
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
        help_text="For forms, graphs, tool outputs, structured AI response, etc.",
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
        ChatTopic,
        on_delete=models.CASCADE,
        related_name="read_markers",
    )

    last_read_message = models.ForeignKey(
        ChatMessage,
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
        ChatMessage,
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
        ChatMessage,
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