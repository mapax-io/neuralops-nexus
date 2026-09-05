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

    To switch embedding providers:
      - fastembed  -> runs nomic-embed-text-v1.5 inside nexus-ai (ONNX, no extra service)
      - litellm    -> routes to Ollama, OpenAI, Infinity, etc. via embedding_base_url

    NOTE on embeddings vs. completions: chat completion no longer goes
    through LiteLLM (see ModelConfig below -- pydantic-ai now), but that
    does NOT affect this field. Embeddings are a separate code path in
    nexus-ai (apps/implementations/embedding/) and litellm remains a valid
    embedding provider there.
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
    # pydantic-ai format ("provider:model"), NOT the old LiteLLM
    # "provider/model". Existing values are converted in migration 0015.
    # Only consulted if a persona somehow has no ModelConfig -- which
    # Persona.model being NOT NULL now makes unreachable -- so this is
    # effectively an operator-visible house default, nothing more.
    default_llm_model = models.CharField(
        max_length=255,
        default="anthropic:claude-haiku-4-5-20251001",
        help_text="Fallback LLM, in pydantic-ai 'provider:model' format.",
    )

    # -- Session --------------------------------------------------------------
    session_timeout_minutes = models.PositiveIntegerField(
        default=30,
        help_text="How long an @session stays active without explicit close (minutes).",
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


class ModelConfig(TenantBaseModel):
    """
    Credentials + identity for ONE model endpoint. Was `AIModel`.

    Deliberately narrow: this row answers "which model, and how do I reach
    it" and nothing else. Generation settings (temperature, max_tokens) are
    NOT here -- they live on Persona, because two personas sharing one API
    key routinely want different settings, which the old design made
    impossible.

    ── provider / model_id are stored SEPARATELY, on purpose ──────────────
    Calls used to route through LiteLLM, whose model string is
    "provider/model" ("anthropic/claude-haiku-4-5-20251001"). They now route
    through pydantic-ai, whose string is "provider:model". Rather than store
    a combined string in either dialect -- and rewrite every row the next
    time a dependency changes its separator -- provider and the BARE model
    name are two columns, and the wire format is composed at the boundary by
    `qualified_id`. Migration 0015 splits the existing LiteLLM strings.

    A ModelConfig is company-owned and made visible to a project via the
    `projects` M2M. It is the ONE AI resource that is genuinely shareable
    across projects -- MCPServer and Persona are both single-project FKs.
    Attaching is a separate, lighter right (model_config.attach) than
    creating, because attaching never touches the API key.
    """

    class Provider(models.TextChoices):
        OPENAI            = "openai",            "OpenAI"
        ANTHROPIC         = "anthropic",         "Anthropic"
        GOOGLE            = "google",            "Google (Gemini)"
        OLLAMA            = "ollama",            "Ollama (local)"
        # Everything reachable with an OpenAI-shaped API plus an api_base:
        # vLLM, LM Studio, OpenRouter, Together, Groq, Fireworks, Mistral,
        # DeepSeek, Azure OpenAI. One entry rather than one per vendor --
        # they are all constructed the same way, and adding a vendor should
        # not require a migration.
        OPENAI_COMPATIBLE = "openai_compatible", "OpenAI-compatible endpoint"
        # RETIRED in migration 0015: "litellm", "local".

    name = models.CharField(
        max_length=255,
        help_text="Human-readable name, e.g. 'Claude Haiku (prod)'.",
    )

    provider = models.CharField(
        max_length=50,
        choices=Provider.choices,
        default=Provider.OPENAI,
        db_index=True,
    )

    model_id = models.CharField(
        max_length=255,
        help_text=(
            "BARE model name -- no provider prefix, no separator. "
            "e.g. 'gpt-4o', 'claude-haiku-4-5-20251001', 'gemini-2.0-flash', "
            "'llama3'. The 'provider:model' string handed to pydantic-ai is "
            "composed by qualified_id."
        ),
    )

    api_base = models.URLField(
        null=True,
        blank=True,
        help_text=(
            "Custom endpoint. Required for provider=openai_compatible; "
            "optional for ollama; unused for the native providers unless "
            "proxying."
        ),
    )

    # -- API Key (encrypted at rest) ------------------------------------------
    # Fernet-encrypted base64 string. Use set_api_key() / get_api_key().
    api_key_encrypted = models.TextField(
        null=True,
        blank=True,
        help_text="Fernet-encrypted API key. Do not set directly — use set_api_key().",
    )

    licence_accepted = models.BooleanField(
        default=False,
        help_text="User must accept the provider's terms of service before this model is active.",
    )

    context_window = models.PositiveIntegerField(default=8192)

    supports_tools = models.BooleanField(
        default=False,
        help_text=(
            "Whether this model can call tools. Load-bearing now: a persona "
            "may only mount MCP servers on a tool-capable model."
        ),
    )
    supports_streaming = models.BooleanField(default=True)
    supports_vision    = models.BooleanField(default=False)
    supports_audio     = models.BooleanField(default=False)

    description = models.TextField(null=True, blank=True)

    config = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional provider-specific runtime configuration.",
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_model_configs",
    )

    # -- Project attachment (visibility) ---------------------------------------
    # Unattached by default -- invisible to every project until a company
    # admin explicitly attaches it. Company-wide visibility
    # (model_config.list) still sees everything regardless; this governs the
    # narrow/project-scoped fallback in
    # authn/permissions/row_rules.py:visible_model_configs().
    projects = models.ManyToManyField(
        "nucleus.Project",
        blank=True,
        related_name="model_configs",
            help_text=(
        "Projects this model config is attached to / visible from. Every "
        "attached project must belong to the same company as this config -- "
        "enforced in intelligence/services.py, NOT by the database (Django "
        "cannot constrain an auto-generated M2M through-table)."
    ),
    )

    # REMOVED (were on AIModel):
    #   temperature, max_tokens  -> moved to Persona
    #   secret_ref               -> never read by any code path

    @property
    def qualified_id(self) -> str:
        """
        The model string pydantic-ai expects: 'anthropic:claude-haiku-4-5-20251001'.

        The ONE place the wire format is assembled. If a dependency changes
        its separator again, this property changes and no row does.
        """
        return f"{self.provider}:{self.model_id}"

    class Meta:
        db_table = "intelligence_model_config"

        constraints = [
            models.UniqueConstraint(
                fields=["company", "name"],
                name="uniq_model_config_name_per_company",
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
        return f"{self.name} ({self.qualified_id})"


class AIRequestLog(TenantBaseModel):
    """
    Logs every model call made by nexus-ai.
    Written by nexus-ai via POST /internal/ai-request-logs/ after each completion.
    Records the exact prompt sent and the raw response received.

    NOTE: model_id/provider are plain strings, NOT an FK to ModelConfig --
    deliberately, so a log row survives its ModelConfig being deleted. The
    trade-off is that you cannot join a log back to the row that served it.
    """

    class Status(models.TextChoices):
        SUCCESS = "success", "Success"
        ERROR   = "error",   "Error"

    # -- Trigger context ------------------------------------------------------
    job_id  = models.CharField(max_length=64, db_index=True)
    msg_id  = models.CharField(max_length=64, db_index=True)

    persona = models.ForeignKey(
        "nucleus.Persona",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="request_logs",
    )

    # -- Model identity -------------------------------------------------------
    model_id = models.CharField(max_length=255)   # e.g. "claude-haiku-4-5-20251001"
    provider = models.CharField(max_length=50)    # e.g. "anthropic"

    # -- Payload --------------------------------------------------------------
    prompt   = models.JSONField()                 # full messages array sent
    response = models.TextField(blank=True)       # raw text received

    # -- Stats ----------------------------------------------------------------
    prompt_tokens     = models.PositiveIntegerField(default=0)
    completion_tokens = models.PositiveIntegerField(default=0)
    latency_ms        = models.PositiveIntegerField(default=0)

    # -- Status ---------------------------------------------------------------
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.SUCCESS,
        db_index=True,
    )
    error = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "intelligence_ai_request_log"
        indexes = [
            models.Index(fields=["company", "persona"]),
            models.Index(fields=["company", "created_at"]),
            models.Index(fields=["job_id"]),
            models.Index(fields=["msg_id"]),
        ]

    def __str__(self):
        return f"[{self.status}] {self.provider}:{self.model_id} job={self.job_id}"


class Persona(TenantBaseModel):
    """
    User-like AI identity -- and, since AIAgent was removed, the ONLY
    composite object in the AI layer.

    A Persona is:
        exactly one   ModelConfig   (`model`)
        zero or one   ModelConfig   (`advisor_model`)
        zero or more  MCPServer     (`mcp_servers`)

    "Agent-ness" is emergent, not a separate record: a persona with no MCP
    servers is a plain LLM; a persona with one or more has tools. This
    replaces the old source_type='model' | 'agent' discriminator and the
    AIAgent row that existed only to pair one model with one MCP server.

    ── Why the FK is called `model`, not `model_config` ──────────────────
    Django is fine with either, but every API schema in this codebase is
    Django Ninja, i.e. Pydantic v2, and Pydantic RESERVES `model_config`
    (it is BaseModel's own config attribute). Declaring a Pydantic field
    named `model_config` raises PydanticUserError at import time, so no
    schema could ever expose it under that name. Keeping the ORM attribute
    as `model` keeps ORM and API aligned and, as a bonus, meant no
    RenameField was needed when AIModel became ModelConfig.

    ── The advisor ───────────────────────────────────────────────────────
    `advisor_model` is the model behind pydantic-ai-harness's Advisor
    capability -- "a second opinion from another model when stuck". It is a
    CAPABILITY the primary model invokes on demand, not a pipeline stage
    this backend orchestrates: nucleus only names the ModelConfig and ships
    its credentials in the internal payload. Nothing here runs a second
    pass, and streaming is unaffected.
    """

    identity_user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="persona_profile",
    )

    # -- Project ownership -----------------------------------------------------
    # Personas are exclusive to one project -- not shared, not visible, not
    # usable from any other project. A real FK because ownership here is
    # strictly single-valued and DB-enforced.
    project = models.ForeignKey(
        "nucleus.Project",
        on_delete=models.CASCADE,
        related_name="personas",
        help_text="The single project this persona belongs to.",
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_personas",
    )

    name = models.CharField(max_length=255)

    description = models.TextField(null=True, blank=True)

    # -- What backs this persona ----------------------------------------------
    model = models.ForeignKey(
        ModelConfig,
        on_delete=models.PROTECT,
        related_name="personas",
        help_text="The primary model. Required.",
    )

    advisor_model = models.ForeignKey(
        ModelConfig,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="advisor_personas",
        help_text=(
            "Optional second model, exposed to the primary as the Advisor "
            "capability -- a second opinion when it gets stuck."
        ),
    )

    mcp_servers = models.ManyToManyField(
        "nucleus.MCPServer",
        blank=True,
        related_name="personas",
        help_text=(
            "Tool servers this persona mounts. Zero or more. Every attached "
            "server must belong to this persona's project -- enforced in "
            "intelligence/services.py, since Django cannot express a "
            "cross-FK constraint like that in the database."
        ),
    )

    # -- Generation settings (moved here from AIModel / AIAgent) ---------------
    # Per-persona, not per-model: two personas sharing one API key routinely
    # want different temperatures, which was impossible while these lived on
    # the model row.
    temperature = models.FloatField(default=0.7)

    max_tokens = models.PositiveIntegerField(default=4096)

    max_steps = models.PositiveIntegerField(
        default=10,
        help_text=(
            "Maximum agent rounds (tool-call iterations) per trigger. Was "
            "AIAgent.max_steps, which the runner never actually read -- it "
            "looked the attribute up on a config object that did not carry "
            "it, so every run silently used the default."
        ),
    )

    avatar = models.ImageField(
        upload_to="personas/%Y/%m/",
        null=True,
        blank=True,
    )

    # REMOVED:
    #   source_type  -- the model/agent discriminator; no longer meaningful
    #   agent        -- AIAgent is deleted

    class Meta:
        db_table = "intelligence_persona"
        constraints = [
            models.UniqueConstraint(
                fields=["project", "name"],
                name="uniq_persona_name_per_project",
            ),
            # An advisor that IS the primary model is a configuration mistake,
            # not a valid setup -- it would just ask the same model twice.
            models.CheckConstraint(
                name="persona_advisor_differs_from_model",
                condition=(
                    models.Q(advisor_model__isnull=True)
                    | ~models.Q(advisor_model=models.F("model"))
                ),
            ),
            # REMOVED: persona_model_or_agent_required (the source_type XOR)
        ]
        indexes = [
            models.Index(fields=["company", "is_active"]),
            models.Index(fields=["project"]),
            models.Index(fields=["model"]),
        ]

    def __str__(self):
        return self.name


class MCPServer(TenantBaseModel):
    """
    MCP server/backend a Persona can mount as a tool source.

    It can represent:
    - local stdio MCP server
    - Docker-based MCP server
    - Kubernetes service
    - remote HTTP MCP server
    - remote SSE MCP server
    - external hosted MCP provider

    ── Project ownership is a real FK now ─────────────────────────────────
    This used to be a ManyToMany to Project that application code restricted
    to exactly one entry. That was a workaround, and it cost a real
    constraint: Django cannot express uniqueness across an M2M through-table,
    so there was NO name uniqueness on this model at all -- not per project,
    not per company -- and the collision check lived in
    intelligence/services.py instead. With a plain FK,
    uniq_mcp_server_name_per_project below does the job properly and that
    manual check is gone.

    A server belongs to exactly one project and is not transferable. Other
    projects register their own.
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

    class AuthType(models.TextChoices):
        NONE           = "none",           "None"
        STATIC_SECRETS = "static_secrets", "Static Secrets"
        OAUTH2         = "oauth2",         "OAuth2"

    name = models.CharField(max_length=255)

    description = models.TextField(null=True, blank=True)

    # -- Project ownership (single project, DB-enforced) -----------------------
    project = models.ForeignKey(
        "nucleus.Project",
        on_delete=models.CASCADE,
        related_name="mcp_servers",
        help_text="The single project this MCP server belongs to. Not transferable.",
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

    # -- Secrets (encrypted at rest) -------------------------------------------
    # Same pattern as ModelConfig.api_key_encrypted (see _fernet() above).
    # Stored as a Fernet-encrypted JSON dict rather than a single string
    # because stdio addons commonly need more than one env var at spawn time
    # -- e.g. {"GITHUB_PERSONAL_ACCESS_TOKEN": "..."} for GitHub,
    # {"AWS_ACCESS_KEY_ID": "...", "AWS_SECRET_ACCESS_KEY": "..."} for AWS.
    # Use set_secrets()/get_secrets().
    secrets_encrypted = models.TextField(
        null=True,
        blank=True,
        help_text="Fernet-encrypted JSON dict of secret env vars. Do not set directly — use set_secrets().",
    )

    auth_type = models.CharField(
        max_length=20,
        choices=AuthType.choices,
        default=AuthType.STATIC_SECRETS,
        db_index=True,
    )

    # Non-secret OAuth metadata only — token_endpoint, authorize_endpoint,
    # client_id, scopes, expires_at. Actual tokens (access_token,
    # refresh_token, client_secret) go through secrets_encrypted via
    # set_secrets().
    oauth_config = models.JSONField(null=True, blank=True)

    is_protected = models.BooleanField(default=False)
    is_default   = models.BooleanField(default=False)

    timeout_seconds = models.PositiveIntegerField(default=60)
    max_retries     = models.PositiveIntegerField(default=3)

    # -- M8: embedding control ------------------------------------------------
    is_first_party = models.BooleanField(
        default=False,
        help_text="True = marketplace-published MCP (we own it). "
                  "False = external/third-party (no embedding allowed).",
    )

    embed_output = models.BooleanField(
        default=False,
        help_text="Opt-in: embed MCP tool results to ChromaDB. "
                  "Only meaningful when is_first_party=True.",
    )

    # REMOVED:
    #   projects (M2M)  -> replaced by the `project` FK above
    #   secret_ref      -> never read by any code path

    class Meta:
        db_table = "intelligence_mcp_server"
        constraints = [
            # Now expressible, because ownership is an FK rather than an M2M.
            models.UniqueConstraint(
                fields=["project", "name"],
                name="uniq_mcp_server_name_per_project",
            ),
            models.CheckConstraint(
                name="mcp_stdio_requires_command",
                condition=(
                    ~models.Q(transport="stdio")
                    | models.Q(command__isnull=False)
                ),
            ),
            models.CheckConstraint(
                name="mcp_http_sse_ws_requires_url",
                condition=(
                    ~models.Q(transport__in=["http", "sse", "websocket"])
                    | models.Q(url__isnull=False)
                ),
            ),
        ]
        indexes = [
            models.Index(fields=["company", "server_type"]),
            models.Index(fields=["company", "transport"]),
            models.Index(fields=["project", "is_active"]),
            models.Index(fields=["company", "is_active"]),
        ]

    def set_secrets(self, secrets: dict) -> None:
        """Encrypt and store a dict of secret env vars (e.g. GITHUB_PERSONAL_ACCESS_TOKEN)."""
        import json
        self.secrets_encrypted = _fernet().encrypt(json.dumps(secrets).encode()).decode()

    def get_secrets(self) -> dict:
        """Decrypt and return the secret env vars dict, or {} if not set."""
        import json
        if not self.secrets_encrypted:
            return {}
        return json.loads(_fernet().decrypt(self.secrets_encrypted.encode()).decode())

    def __str__(self):
        return self.name
