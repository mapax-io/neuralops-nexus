"""
Schemas for ModelConfig, MCPServer, Persona, Prompt, and PromptTemplate APIs.

── A naming constraint worth knowing about ───────────────────────────────
Django Ninja schemas are Pydantic v2, and Pydantic RESERVES `model_config`
-- it is BaseModel's own configuration attribute. Declaring a field with
that name raises PydanticUserError at IMPORT time:

    `model_config` cannot be used as a model field name.

So the Django FK is `Persona.model` / `Persona.advisor_model`, and the
schemas expose `model` / `advisor_model` on output. Input still uses
`model_config_id` / `advisor_model_config_id`, which is fine -- only the
exact name `model_config` is reserved, the `model_` prefix merely triggers
a protected-namespace warning that these do not hit.
"""
from typing import Optional
from ninja import Schema
from pydantic import Field


# ── ModelConfig ───────────────────────────────────────────────────────────────

class ModelConfigIn(Schema):
    name: str
    provider: str          # openai | anthropic | google | ollama | openai_compatible
    model_id: str          # BARE model name -- no provider prefix, no separator
    api_key: Optional[str] = None
    api_base: Optional[str] = None
    description: Optional[str] = None
    licence_accepted: bool = False
    context_window: int = 8192
    supports_tools: bool = False
    supports_streaming: bool = True
    supports_vision: bool = False
    supports_audio: bool = False
    config: dict = {}
    # REMOVED: temperature, max_tokens -> now per-persona
    # REMOVED: secret_ref              -> never read by any code path


class ModelConfigPatchIn(Schema):
    """
    provider and model_id ARE patchable. Changing either repoints every persona
    that uses this row at the new model the moment it saves -- that is the
    intended way to move personas to a successor model without deleting and
    recreating the config (which the delete guard refuses while personas
    reference it). The UI warns before saving; the server keeps the same
    guards as create: a known provider, and a bare model_id with no prefix.
    """
    name: Optional[str] = None
    provider: Optional[str] = None     # openai | anthropic | google | ollama | openai_compatible
    model_id: Optional[str] = None     # BARE model name -- no provider prefix, no separator
    api_key: Optional[str] = None      # write-only, re-encrypted on set
    api_base: Optional[str] = None
    description: Optional[str] = None
    context_window: Optional[int] = None
    supports_tools: Optional[bool] = None
    supports_streaming: Optional[bool] = None
    supports_vision: Optional[bool] = None
    supports_audio: Optional[bool] = None
    config: Optional[dict] = None


class ModelConfigOut(Schema):
    id: str
    name: str
    provider: str
    model_id: str
    qualified_id: str                  # "openai:gpt-4o-mini"
    api_base: Optional[str] = None
    description: Optional[str] = None
    licence_accepted: bool
    context_window: int
    supports_tools: bool
    supports_streaming: bool
    supports_vision: bool
    supports_audio: bool
    config: dict
    is_active: bool
    has_api_key: bool
    # Projects this config is attached to (visibility gate) -- lets clients
    # render and manage attachments without a second endpoint.
    project_ids: list[str] = []


class ModelConfigRef(Schema):
    """Compact form, embedded in PersonaOut."""
    id: str
    name: str
    provider: str
    model_id: str
    qualified_id: str
    supports_tools: bool               # lets the UI grey out MCP attachment


# ── MCPServer ─────────────────────────────────────────────────────────────────

class MCPOAuthAuthorizeOut(Schema):
    authorize_url: str


class MCPServerIn(Schema):
    name: str
    description: Optional[str] = None
    project_id: str        # MCP servers are project-owned (a real FK now)
    server_type: str = "remote"
    transport: str = "http"
    url: Optional[str] = None
    command: Optional[str] = None
    docker_image: Optional[str] = None
    docker_command: Optional[str] = None
    kubernetes_service: Optional[str] = None
    config: dict = {}
    timeout_seconds: int = 60
    max_retries: int = 3
    is_first_party: bool = False
    embed_output: bool = False
    # oauth configuration
    auth_type: str = "static_secrets"
    oauth_config: Optional[dict] = None
    client_secret: Optional[str] = None  # write-only -- folded into secrets_encrypted
    # REMOVED: secret_ref


class MCPServerPatchIn(Schema):
    name: Optional[str] = None
    description: Optional[str] = None
    url: Optional[str] = None
    command: Optional[str] = None
    docker_image: Optional[str] = None
    docker_command: Optional[str] = None
    kubernetes_service: Optional[str] = None
    config: Optional[dict] = None
    timeout_seconds: Optional[int] = None
    max_retries: Optional[int] = None
    embed_output: Optional[bool] = None
    # oauth configuration
    auth_type: Optional[str] = None
    oauth_config: Optional[dict] = None
    client_secret: Optional[str] = None


class MCPServerOut(Schema):
    id: str
    name: str
    description: Optional[str] = None
    project_id: str                    # non-null now -- it is a real FK
    server_type: str
    transport: str
    url: Optional[str] = None
    command: Optional[str] = None
    docker_image: Optional[str] = None
    config: dict
    timeout_seconds: int
    max_retries: int
    is_first_party: bool
    embed_output: bool
    is_active: bool
    # oauth configuration
    auth_type: str
    oauth_connected: bool
    # Non-secret OAuth config (client_id, endpoints, scopes, token_env_var) so
    # the frontend can pre-fill the edit form. Secrets/tokens live in
    # secrets_encrypted and are never returned here.
    oauth_config: Optional[dict] = None


class MCPServerRef(Schema):
    """Compact form, embedded in PersonaOut."""
    id: str
    name: str
    transport: str
    auth_type: str
    oauth_connected: bool              # so the UI can flag one needing reconnect


# ── Prompt ────────────────────────────────────────────────────────────────────

class PromptIn(Schema):
    system_prompt: str
    output_type: str = "text"
    context_scope: Optional[list] = None
    template_id: Optional[str] = None


class PromptOut(Schema):
    id: str
    system_prompt: str
    output_type: str
    context_scope: Optional[list] = None
    template_id: Optional[str] = None


class ListTemplatePrompts(Schema):
    prompts: dict[str, str]


class TemplatePromptContent(Schema):
    content: str


# ── Persona ───────────────────────────────────────────────────────────────────

class PersonaIn(Schema):
    name: str
    description: Optional[str] = None
    project_id: str
    model_config_id: str                            # REQUIRED
    advisor_model_config_id: Optional[str] = None   # 0..1
    mcp_server_ids: list[str] = Field(default_factory=list)   # 0..N
    temperature: float = 0.7
    max_tokens: int = 4096
    max_steps: int = 10
    prompt: PromptIn
    # REMOVED: source_type, model_id, agent_id


class PersonaPatchIn(Schema):
    """
    The backing is mutable now. It was not before -- DECISIONS.md §18 said
    "the agent/model backing the persona cannot be changed after creation --
    delete and recreate if needed" -- which stopped being true the moment
    AIAgent went away and a persona became a plain composition.

    `clear_advisor` exists because handlers use payload.dict(exclude_none=True),
    so None means "not sent" and there is otherwise no way to express
    "remove the advisor". mcp_server_ids does not need the same treatment:
    [] is a distinct, meaningful value there (detach all).
    """
    name: Optional[str] = None
    description: Optional[str] = None
    model_config_id: Optional[str] = None
    advisor_model_config_id: Optional[str] = None
    clear_advisor: bool = False
    mcp_server_ids: Optional[list[str]] = None      # [] clears all
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    max_steps: Optional[int] = None
    prompt: Optional[PromptIn] = None


class PersonaOut(Schema):
    id: str
    name: str
    description: Optional[str] = None
    project_id: str
    # Named `model` / `advisor_model`, NOT `model_config` -- see module docstring.
    model: ModelConfigRef
    advisor_model: Optional[ModelConfigRef] = None
    mcp_servers: list[MCPServerRef] = Field(default_factory=list)
    temperature: float
    max_tokens: int
    max_steps: int
    prompt: Optional[PromptOut] = None
    is_active: bool
    # Server-relative media URL of the shadow user's assigned avatar --
    # personas already show it in chat; management UIs need it too.
    avatar: Optional[str] = None
    # REMOVED: source_type, model_id, agent_id


# ── PromptTemplate ────────────────────────────────────────────────────────────

class PromptTemplateOut(Schema):
    id: str
    title: str
    description: str
    system_prompt: str
    output_type: str
    tags: list
    is_featured: bool


# ── AIRequestLog ─────────────────────────────────────────────────────────────

class AIRequestLogOut(Schema):
    id: str
    job_id: str
    msg_id: str
    persona_id: Optional[str] = None
    model_id: str
    provider: str
    prompt: list
    response: str
    prompt_tokens: int
    completion_tokens: int
    latency_ms: int
    status: str
    error: Optional[str] = None
    created_at: str


# ── CompanyAIConfig ───────────────────────────────────────────────────────────

class CompanyAIConfigIn(Schema):
    embedding_provider: str
    embedding_model: str
    embedding_base_url: str = ""
    default_llm_model: str


class CompanyAIConfigOut(Schema):
    embedding_provider: str
    embedding_model: str
    embedding_base_url: str
    default_llm_model: str
