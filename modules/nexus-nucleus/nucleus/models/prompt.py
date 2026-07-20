from django.db import models

from .base import TenantBaseModel


class PromptTemplate(TenantBaseModel):
    """
    Curated prompt template library.

    Platform-maintained growing library of system prompts.
    Users pick a template and customize it into a Prompt on their Persona.
    Templates are company-scoped — each company manages its own library.
    """

    class OutputType(models.TextChoices):
        TEXT = "text", "Text (Markdown)"
        CODE = "code", "Code"
        HTML = "html", "HTML"
        # MCP servers pre-render their output to HTML — forms, product cards,
        # diagrams, ecommerce results, coding environments, etc. all use "html".
        # New output types are added here only if the FRONTEND needs to handle
        # them differently (e.g. a native code editor vs a sandboxed HTML div).

    title = models.CharField(max_length=255)

    description = models.TextField(
        blank=True,
        default="",
        help_text="Short description shown in the template picker.",
    )

    system_prompt = models.TextField(
        help_text="The actual system prompt content.",
    )

    output_type = models.CharField(
        max_length=20,
        choices=OutputType.choices,
        default=OutputType.TEXT,
        db_index=True,
    )

    tags = models.JSONField(
        default=list,
        blank=True,
        help_text="List of tag strings for filtering (e.g. ['coding', 'python']).",
    )

    is_featured = models.BooleanField(
        default=False,
        help_text="Show this template prominently in the picker.",
    )

    class Meta:
        db_table = "intelligence_prompt_template"
        constraints = [
            models.UniqueConstraint(
                fields=["company", "title"],
                name="uniq_prompt_template_title_per_company",
            )
        ]
        indexes = [
            models.Index(fields=["company", "output_type"]),
            models.Index(fields=["company", "is_featured"]),
            models.Index(fields=["company", "is_active"]),
        ]

    def __str__(self):
        return self.title


class Prompt(TenantBaseModel):
    """
    The active system prompt attached to a Persona.

    One Prompt per Persona (OneToOne).
    Can be created from a PromptTemplate or written from scratch.

    output_type controls how the frontend renders the response:
      text — markdown rendered in a chat bubble
      code — syntax-highlighted code block
      html — sandboxed div; MCP servers return pre-rendered HTML for
             forms, product cards, diagrams, ecommerce results,
             coding environments, class diagrams, network diagrams, etc.

    context_scope optionally restricts which context types
    ContextManager will search (e.g. only doc, only chat).
    If null, all attached context sources are searched.
    """

    class OutputType(models.TextChoices):
        TEXT = "text", "Text (Markdown)"
        CODE = "code", "Code"
        HTML = "html", "HTML"

    persona = models.OneToOneField(
        "nucleus.Persona",
        on_delete=models.CASCADE,
        related_name="prompt",
    )

    system_prompt = models.TextField(
        help_text="System prompt sent to the model on every AI trigger.",
    )

    output_type = models.CharField(
        max_length=20,
        choices=OutputType.choices,
        default=OutputType.TEXT,
        db_index=True,
        help_text="Controls model output format and frontend rendering.",
    )

    context_scope = models.JSONField(
        null=True,
        blank=True,
        help_text=(
            "Optional list of context types to include, e.g. ['chat', 'doc']. "
            "Null means all attached context sources are searched."
        ),
    )

    template = models.ForeignKey(
        PromptTemplate,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="derived_prompts",
        help_text="The template this prompt was created from, if any.",
    )

    class Meta:
        db_table = "intelligence_prompt"
        indexes = [
            models.Index(fields=["company", "output_type"]),
            models.Index(fields=["company", "is_active"]),
        ]

    def __str__(self):
        return f"Prompt for {self.persona.name} ({self.output_type})"
