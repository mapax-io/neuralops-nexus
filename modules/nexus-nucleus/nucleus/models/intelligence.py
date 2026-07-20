from django.conf import settings
from django.db import models
from django.core.exceptions import ImproperlyConfigured

from .base import BaseModel, TenantBaseModel


def _fernet():
    """Return a Fernet instance using FIELD_ENCRYPTION_KEY from settings."""
    try:
        from cryptography.fernet import Fernet
        key = getattr(settings, "FIELD_ENCRYPTION_KEY", None)
        if not key:
            raise ImproperlyConfigured(
                "FIELD_ENCRYPTION_KEY is not set. "
                "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
            )
        return Fernet(key.encode() if isinstance(key, str) else key)
    except ImportError:
        raise ImproperlyConfigured(
            "cryptography package is required for api_key encryption. "
            "Add it to requirements.txt."
        )


class CompanyAIConfig(BaseModel):
    """
    Per-company AI configuration.

    Singleton per company — controls which embedding provider, model,
    and default LLM are used for all AI operations within the company.

    Changeable via API at runtime (no restart required).
    nexus-ai fetches this via internal API and caches per request.

    To switch providers:
      - fastembed  -> runs nomic-embed-text-v1.5 inside nexus-ai (ONNX, no extra service)
      - litellm    -> routes to Ollama, OpenAI, Infinity, etc. via embedding_base_url
    """

    class EmbeddingProvider(models.TextChoices):
        FASTEMBED = "fastembed", "FastEmbed (local ONNX)"
        LITELLM   = "litellm",   "LiteLLM (Ollama / OpenAI / Infinity)"

    company = models.OneToOneField(
        "nucleus.Company",
        on_delete=models.CASCADE,
        related_name="ai_config",
    )

    # -- Embedding ------------------------------------------------------------
    embedding_provider = models.CharField(
        max_length=50,
        choices=EmbeddingProvider.choices,
        default=EmbeddingProvider.FASTEMBED,
    )

    embedding_model = models.CharField(
        max_length=255,
        default="nomic-ai/nomic-embed-text-v1.5",
        help_text="Model name passed to the embedding provider.",
    )

    embedding_base_url = models.URLField(
        blank=True,
        default="",
        help_text="Required when provider=litellm and model runs on Ollama or Infinity.",
    )

    # -- LLM defaults ---------------------------------------------------------
    default_llm_model = models.CharField(
        max_length=255,
        default="anthropic/claude-haiku-4-5-20251001",
        help_text="Fallback LLM model when a persona has no model assigned.",
    )

    # -- Audit ----------------------------------------------------------------
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ai_config_updates",
    )

    class Meta:
        db_table = "intelligence_company_ai_config"
        verbose_name = "Company AI Config"

    def __str__(self):
        return f"{self.company} - {self.embedding_provider}/{self.embedding_model}"


class AIModel(TenantBaseModel):
    """
    LLM configuration stored per company.

    All calls go through LiteLLM — the actual provider (Anthropic, OpenAI,
    Azure, Ollama, etc.) is encoded in model_id using LiteLLM's prefix format:
      "anthropic/claude-haiku-4-5-20251001"
      "openai/gpt-4o"
      "azure/gpt-4"
      "ollama/llama3"  (+ api_base pointing to Ollama service)

    provider=local is reserved for future direct ONNX/llama.cpp runtimes
    that bypass LiteLLM entirely.
    """

    class Provider(models.TextChoices):
        LITELLM = "litellm", "LiteLLM (all cloud/hosted providers)"
        LOCAL   = "local",   "Local (custom ONNX / llama.cpp runtime)"

    name = models.CharField(
        max_length=255,
        help_text="Human-readable model name.",
    )

    provider = models.CharField(
        max_length=50,
        choices=Provider.choices,
        default=Provider.LITELLM,
        db_index=True,
    )

    model_id = models.CharField(
        max_length=255,
        help_text="LiteLLM model string, e.g. 'anthropic/claude-haiku-4-5-20251001'.",
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_ai_models",
    )

    description = models.TextField(
        null=True,
        blank=True,
    )

    api_base = models.URLField(
        null=True,
        blank=True,
        help_text="Optional custom API base URL (e.g. Ollama or self-hosted endpoint).",
    )

    secret_ref = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="Reference to secret manager entry (production: Vault / AWS Secrets Manager).",
    )

    # -- API Key (encrypted at rest) ------------------------------------------
    # Stored as a Fernet-encrypted base64 string.
    # Use set_api_key() to write, get_api_key() to read.
    # For production deployments, prefer secret_ref + a secrets manager.
    api_key_encrypted = models.TextField(
        null=True,
        blank=True,
        help_text="Fernet-encrypted API key. Do not set directly — use set_api_key().",
    )

    licence_accepted = models.BooleanField(
        default=False,
        help_text="User must accept the provider's terms of service before this model is active.",
    )

    temperature = models.FloatField(default=0.7)

    max_tokens = models.PositiveIntegerField(
        default=4096,
    )

    context_window = models.PositiveIntegerField(
        default=8192,
    )

    supports_tools = models.BooleanField(default=False)

    supports_streaming = models.BooleanField(default=True)

    supports_vision = models.BooleanField(default=False)

    supports_audio = models.BooleanField(default=False)

    config = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional provider-specific runtime configuration.",
    )

    class Meta:
        db_table = "intelligence_ai_model"

        constraints = [
            models.UniqueConstraint(
                fields=["company", "name"],
                name="uniq_ai_model_name_per_company",
            )
        ]

        indexes = [
            models.Index(fields=["company", "provider"]),
            models.Index(fields=["company", "is_active"]),
        ]

    def set_api_key(self, raw_key: str) -> None:
        """Encrypt and store an API key."""
        self.api_key_encrypted = _fernet().encrypt(raw_key.encode()).decode()

    def get_api_key(self) -> str | None:
        """Decrypt and return the API key, or None if not set."""
        if not self.api_key_encrypted:
            return None
        return _fernet().decrypt(self.api_key_encrypted.encode()).decode()

    def __str__(self):
        return f"{self.name} ({self.model_id})"


class AIAgent(TenantBaseModel):
    class AgentType(models.TextChoices):
        INTERNAL = "internal", "Internal"
        EXTERNAL = "external", "External"

    name = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True)

    agent_type = models.CharField(
        max_length=20,
        choices=AgentType.choices,
        default=AgentType.INTERNAL,
        db_index=True,
    )

    model = models.ForeignKey(
        "nucleus.AIModel",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="agents",
    )

    mcp_server = models.ForeignKey(
        "nucleus.MCPServer",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="agents",
    )

    external_url = models.URLField(
        null=True,
        blank=True,
        help_text="Remote/online agent endpoint.",
    )

    secret_ref = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="Secret manager reference for external agent credentials.",
    )

    system_prompt = models.TextField(
        null=True,
        blank=True,
        help_text="Internal agent execution rules. External agents may ignore this.",
    )

    safety_mode = models.BooleanField(default=True)
    max_steps = models.PositiveIntegerField(default=5)
    allow_parallel_tools = models.BooleanField(default=False)

    class Meta:
        db_table = "intelligence_ai_agent"
        constraints = [
            models.UniqueConstraint(
                fields=["company", "name"],
                name="uniq_ai_agent_name_per_company",
            ),
            models.CheckConstraint(
                name="internal_agent_requires_model",
                check=(
                    ~models.Q(agent_type="internal")
                    | models.Q(model__isnull=False)
                ),
            ),
            models.CheckConstraint(
                name="external_agent_requires_url",
                check=(
                    ~models.Q(agent_type="external")
                    | models.Q(external_url__isnull=False)
                ),
            ),
        ]
        indexes = [
            models.Index(fields=["company", "agent_type"]),
            models.Index(fields=["company", "model"]),
            models.Index(fields=["company", "mcp_server"]),
            models.Index(fields=["company", "is_active"]),
        ]

    def __str__(self):
        return self.name


class Persona(TenantBaseModel):
    """
    User-like AI identity.

    Persona wraps either one AIModel or one AIAgent
    and exposes it as a chat participant.
    """

    class SourceType(models.TextChoices):
        MODEL = "model", "Model"
        AGENT = "agent", "Agent"

    identity_user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="persona_profile",
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_personas",
    )

    name = models.CharField(max_length=255)

    description = models.TextField(
        null=True,
        blank=True,
    )

    source_type = models.CharField(
        max_length=20,
        choices=SourceType.choices,
        db_index=True,
    )

    model = models.ForeignKey(
        AIModel,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="personas",
    )

    agent = models.ForeignKey(
        AIAgent,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="personas",
    )

    avatar = models.ImageField(
        upload_to="personas/%Y/%m/",
        null=True,
        blank=True,
    )

    class Meta:
        db_table = "intelligence_persona"
        constraints = [
            models.UniqueConstraint(
                fields=["company", "name"],
                name="uniq_persona_name_per_company",
            ),
            models.CheckConstraint(
                name="persona_model_or_agent_required",
                check=(
                    models.Q(
                        source_type="model",
                        model__isnull=False,
                        agent__isnull=True,
                    )
                    |
                    models.Q(
                        source_type="agent",
                        agent__isnull=False,
                        model__isnull=True,
                    )
                ),
            ),
        ]
        indexes = [
            models.Index(fields=["company", "source_type"]),
            models.Index(fields=["company", "is_active"]),
        ]

    def __str__(self):
        return self.name


class MCPServer(TenantBaseModel):
    """
    MCP server/backend used by internal agents.

    It can represent:
    - local stdio MCP server
    - Docker-based MCP server
    - Kubernetes service
    - remote HTTP MCP server
    - remote SSE MCP server
    - external hosted MCP provider
    """

    class ServerType(models.TextChoices):
        LOCAL      = "local",      "Local"
        DOCKER     = "docker",     "Docker"
        KUBERNETES = "kubernetes", "Kubernetes"
        REMOTE     = "remote",     "Remote"
        HOSTED     = "hosted",     "Hosted / Online"

    class Transport(models.TextChoices):
        STDIO     = "stdio",     "STDIO"
        HTTP      = "http",      "HTTP"
        SSE       = "sse",       "SSE"
        WEBSOCKET = "websocket", "WebSocket"

    name = models.CharField(max_length=255)

    description = models.TextField(
        null=True,
        blank=True,
    )

    server_type = models.CharField(
        max_length=30,
        choices=ServerType.choices,
        default=ServerType.REMOTE,
        db_index=True,
    )

    transport = models.CharField(
        max_length=30,
        choices=Transport.choices,
        default=Transport.HTTP,
        db_index=True,
    )

    command = models.TextField(
        null=True,
        blank=True,
        help_text="Command for local/stdio MCP server.",
    )

    url = models.URLField(
        null=True,
        blank=True,
        help_text="URL for HTTP/SSE/WebSocket MCP server.",
    )

    docker_image = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="Docker image for Docker-based MCP server.",
    )

    docker_command = models.TextField(
        null=True,
        blank=True,
        help_text="Optional Docker run command or entrypoint override.",
    )

    kubernetes_service = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="Kubernetes service name or internal DNS.",
    )

    config = models.JSONField(
        default=dict,
        blank=True,
        help_text="Non-secret MCP configuration.",
    )

    secret_ref = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="Secret manager reference. Do not store raw credentials.",
    )

    timeout_seconds = models.PositiveIntegerField(default=60)

    max_retries = models.PositiveIntegerField(default=3)

    class Meta:
        db_table = "intelligence_mcp_server"
        constraints = [
            models.UniqueConstraint(
                fields=["company", "name"],
                name="uniq_mcp_server_name_per_company",
            ),
            models.CheckConstraint(
                name="mcp_stdio_requires_command",
                check=(
                    ~models.Q(transport="stdio")
                    | models.Q(command__isnull=False)
                ),
            ),
            models.CheckConstraint(
                name="mcp_http_sse_ws_requires_url",
                check=(
                    ~models.Q(transport__in=["http", "sse", "websocket"])
                    | models.Q(url__isnull=False)
                ),
            ),
        ]
        indexes = [
            models.Index(fields=["company", "server_type"]),
            models.Index(fields=["company", "transport"]),
            models.Index(fields=["company", "is_active"]),
        ]

    def __str__(self):
        return self.name
