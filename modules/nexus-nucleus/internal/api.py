"""
Internal API — called by nexus-ai only, not exposed to users.
Authenticated via X-Internal-API-Key header (set in INTERNAL_API_KEY env var).

nginx returns 403 for /api/v1/internal/ (see neuralops/nginx.conf): nexus-ai
reaches these endpoints container-to-container over the Docker network and
never through the proxy, and the responses carry decrypted API keys and raw
chat history.
"""

import os
from pydantic import Field
from ninja import Router, Schema
from ninja.errors import HttpError
from ninja.security import APIKeyHeader
from typing import Optional


class InternalAPIKey(APIKeyHeader):
    param_name = "X-Internal-API-Key"

    def authenticate(self, request, key: str):
        expected = os.getenv("INTERNAL_API_KEY", "change-me-in-production")
        if key == expected:
            return key
        return None


internal_auth = InternalAPIKey()
router = Router(tags=["Internal"], auth=internal_auth)


# ── Response schemas ──────────────────────────────────────────────────────────


class MCPServerInternal(Schema):
    id: str
    name: str
    server_type: str
    transport: str
    url: Optional[str] = None
    command: Optional[str] = None
    config: dict
    # Decrypted secret env vars (e.g. GITHUB_PERSONAL_ACCESS_TOKEN) -- same
    # trust boundary as ModelInternal.api_key below: only ever sent over the
    # internal network to nexus-ai, which forwards them as subprocess env
    # vars when spawning a stdio MCP server, never into the command string.
    secrets: dict = Field(default_factory=dict)
    is_first_party: bool = False
    embed_output: bool = False
    needs_reauth: bool = False
    # Which auth style this server uses, and -- for oauth2 -- which key in
    # `secrets` holds the bearer access token nexus-ai should send on HTTP/
    # SSE requests (stdio servers get the whole `secrets` dict as subprocess
    # env instead, so this is only consumed on the non-stdio path).
    auth_type: str = "static_secrets"
    token_env_var: str = "OAUTH_ACCESS_TOKEN"


class PromptInternal(Schema):
    system_prompt: str
    output_type: str
    context_scope: Optional[list] = None


class ModelInternal(Schema):
    """
    One model endpoint, ready to use.

    `qualified_id` is the pydantic-ai model string ("anthropic:claude-haiku-
    4-5-20251001"), composed server-side by ModelConfig.qualified_id. It is
    sent pre-assembled deliberately: provider and model_id are stored as
    separate columns precisely so no consumer has to know which separator
    the current model library expects, and that knowledge should not leak
    across the boundary either.

    temperature/max_tokens are NOT here -- they are per-persona now, not per
    model row, and live on PersonaInternal.
    """
    id: str
    name: str
    provider: str          # openai | anthropic | google | ollama | openai_compatible
    model_id: str          # BARE name, no prefix
    qualified_id: str      # "provider:model" -- hand straight to pydantic-ai
    api_base: Optional[str] = None
    api_key: Optional[str] = None  # decrypted — only sent over internal network
    context_window: int
    supports_tools: bool
    supports_streaming: bool
    supports_vision: bool


class PersonaInternal(Schema):
    """
    Everything nexus-ai needs to run one persona. Since AIAgent was removed,
    this is the whole configuration -- there is no second lookup.

    `advisor_model` is the model behind pydantic-ai-harness's Advisor
    capability: a second opinion the PRIMARY model asks for when it gets
    stuck. It is not a pipeline stage nucleus orchestrates -- nucleus just
    names the model and ships its credentials. None when unconfigured.

    `mcp_servers` is genuinely 0..N now. It used to come from
    AIAgent.mcp_server, a single FK, so it was never longer than one entry
    even though the consumer side has always handled a list.
    """
    id: str
    name: str
    prompt: PromptInternal
    model: ModelInternal
    advisor_model: Optional[ModelInternal] = None
    mcp_servers: list[MCPServerInternal] = Field(default_factory=list)
    temperature: float
    max_tokens: int
    max_steps: int


class ContextSourceInternal(Schema):
    id: str
    type: str  # "doc" or "code"
    label: str
    collection_id: str


class AIRequestLogIn(Schema):
    job_id: str
    msg_id: str
    persona_id: Optional[str] = None
    model_id: str
    provider: str
    prompt: list
    response: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: int = 0
    status: str = "success"
    error: Optional[str] = None


class AIConfigInternal(Schema):
    embedding_provider: str
    embedding_model: str
    embedding_base_url: str
    default_llm_model: str


class HistoryMessageInternal(Schema):
    """
    Raw message data -- deliberately NOT role-mapped or filtered here.
    Deciding "is this human/persona/system", "does this look like valid
    rendered HTML", "should a visual-type-rendered-as-text reply be shown
    as history" are all prompt-quality judgment calls, not chat-orchestration
    ones -- nexus-ai makes them (see apps/managers/nucleus_client.py).
    """
    id: str
    sender_type: str        # "human" | "persona" | "system"
    sender_name: Optional[str] = None
    content: str
    render_as: str = "text"
    output_type: str = "text"
    sequence: int


# ── Helpers ───────────────────────────────────────────────────────────────────


def _model_internal(model) -> ModelInternal:
    """Serialise one ModelConfig, decrypting its API key."""
    return ModelInternal(
        id=str(model.id),
        name=model.name,
        provider=model.provider,
        model_id=model.model_id,
        qualified_id=model.qualified_id,
        api_base=model.api_base,
        api_key=model.get_api_key(),
        context_window=model.context_window,
        supports_tools=model.supports_tools,
        supports_streaming=model.supports_streaming,
        supports_vision=model.supports_vision,
    )


def _mcp_internal(server, needs_reauth: bool) -> MCPServerInternal:
    return MCPServerInternal(
        id=str(server.id),
        name=server.name,
        server_type=server.server_type,
        transport=server.transport,
        url=server.url,
        command=server.command,
        config=server.config,
        # A server that needs re-authentication gets NO secrets -- handing
        # nexus-ai a stale token would produce a 401 it cannot act on. The
        # needs_reauth flag is what the runner raises MCPReauthRequiredError
        # on instead, which surfaces as a reconnect prompt in chat.
        secrets={} if needs_reauth else server.get_secrets(),
        is_first_party=server.is_first_party,
        embed_output=server.embed_output,
        needs_reauth=needs_reauth,
        auth_type=server.auth_type,
        token_env_var=(server.oauth_config or {}).get("token_env_var", "OAUTH_ACCESS_TOKEN"),
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("/personas/{persona_id}/", response=PersonaInternal)
def get_persona_internal(request, persona_id: str):
    """
    Fetch full persona config for nexus-ai to use on trigger.

    Returns: prompt + model (decrypted key) + optional advisor model +
    0..N MCP servers + generation settings.

    No source_type branch any more -- a persona has one model, optionally an
    advisor, and zero or more tool servers. "Agent-ness" is emergent: no MCP
    servers means a plain LLM, which is already how the runner behaves.
    """
    from nucleus.models import Persona
    from intelligence import oauth_client

    persona = (
        Persona.objects.filter(id=persona_id, is_active=True)
        .select_related("prompt", "model", "advisor_model")
        .prefetch_related("mcp_servers")
        .first()
    )

    if not persona:
        raise HttpError(404, "Persona not found.")

    if not hasattr(persona, "prompt") or not persona.prompt:
        raise HttpError(400, "Persona has no prompt configured.")

    # model is NOT NULL at the database level, so this can only fail if the
    # row it points at was soft-deleted. Refusing is deliberate: serving a
    # deleted model's decrypted API key is worse than a clear error, and
    # PROTECT never fires here because every delete in this codebase is a
    # soft delete (is_active=False). intelligence/services.py also refuses
    # to soft-delete a model any persona still uses.
    if persona.model is None or not persona.model.is_active:
        raise HttpError(400, "Persona's model config is missing or deleted.")

    prompt = persona.prompt

    # An advisor pointing at a deleted model degrades rather than fails --
    # it is an optional capability, and losing it should not take the
    # persona down with it.
    advisor = persona.advisor_model
    if advisor is not None and not advisor.is_active:
        advisor = None

    # Per-server, in a loop -- this is the code path that was capped at one
    # entry by AIAgent.mcp_server being a single FK. refresh_if_needed()
    # returns True immediately for any non-oauth2 server and returns early
    # for an oauth2 server whose token is still valid, so iterating is cheap:
    # only an actually-expiring token costs a network round trip.
    mcp_servers = []
    for server in persona.mcp_servers.filter(is_active=True):
        ok = oauth_client.refresh_if_needed(server)
        mcp_servers.append(_mcp_internal(server, needs_reauth=not ok))

    return PersonaInternal(
        id=str(persona.id),
        name=persona.name,
        prompt=PromptInternal(
            system_prompt=prompt.system_prompt,
            output_type=prompt.output_type,
            context_scope=prompt.context_scope,
        ),
        model=_model_internal(persona.model),
        advisor_model=_model_internal(advisor) if advisor else None,
        mcp_servers=mcp_servers,
        temperature=persona.temperature,
        max_tokens=persona.max_tokens,
        max_steps=persona.max_steps,
    )


@router.get("/topics/{topic_id}/contexts/", response=list[ContextSourceInternal])
def get_topic_contexts(request, topic_id: str):
    """
    Fetch all active context sources for a topic.
    nexus-ai calls this when building context for a trigger.
    """
    from nucleus.models import TopicContext

    sources = TopicContext.objects.filter(
        topic__id=topic_id,
        is_active=True,
        collection_id__isnull=False,
    ).exclude(collection_id="")

    return [
        ContextSourceInternal(
            id=str(s.id),
            type=s.context_type,
            label=s.label,
            collection_id=s.collection_id,
        )
        for s in sources
    ]


@router.post("/ai-request-logs/", response={201: dict})
def create_ai_request_log(request, payload: AIRequestLogIn):
    """
    Called by nexus-ai after every model completion.
    Writes a log record with the full prompt + raw response.
    """
    from nucleus.models import AIRequestLog, Persona, Company

    company = Company.objects.filter(is_active=True).first()
    if not company:
        raise HttpError(503, "No company found.")

    persona = None
    if payload.persona_id:
        persona = Persona.objects.filter(id=payload.persona_id, is_active=True).first()

    AIRequestLog.objects.create(
        company=company,
        job_id=payload.job_id,
        msg_id=payload.msg_id,
        persona=persona,
        model_id=payload.model_id,
        provider=payload.provider,
        prompt=payload.prompt,
        response=payload.response,
        prompt_tokens=payload.prompt_tokens,
        completion_tokens=payload.completion_tokens,
        latency_ms=payload.latency_ms,
        status=payload.status,
        error=payload.error,
    )
    return 201, {"ok": True}


@router.get("/topics/{topic_id}/history/", response=list[HistoryMessageInternal])
def get_topic_history_internal(
    request, topic_id: str,
    limit: int = 20,
    exclude_message_id: Optional[str] = None,
):
    """
    Raw recent message history for a topic -- called by nexus-ai itself
    (apps/managers/nucleus_client.py:fetch_history) right before it builds
    a prompt. `limit` is nexus-ai's own call, not something nucleus decides.

    exclude_message_id -- the human message that triggered this particular
    AI run is already saved in the DB by the time this gets called (send_message
    saves it before firing the trigger task), so it would otherwise show up as
    the newest row in its own history. Pass its id here to drop it -- it's
    sent separately as TriggerJob.message, not meant to appear twice.
    """
    from nucleus.models import ChatMessage

    qs = ChatMessage.objects.filter(topic_id=topic_id, is_active=True)
    if exclude_message_id:
        qs = qs.exclude(id=exclude_message_id)

    messages = list(
        qs.select_related("sender").order_by("-sequence")[:limit]
    )

    result = []
    for m in reversed(messages):
        metadata = m.metadata or {}
        sender_type = getattr(m.sender, "user_type", "human") if m.sender else "system"
        sender_name = None
        if m.sender:
            sender_name = metadata.get("persona_name") or m.sender.get_display_name()
        result.append(HistoryMessageInternal(
            id=str(m.id),
            sender_type=sender_type,
            sender_name=sender_name,
            content=m.content or "",
            render_as=metadata.get("render_as", "text"),
            output_type=metadata.get("output_type", "text"),
            sequence=m.sequence,
        ))
    return result


@router.get("/companies/{company_id}/ai-config/", response=AIConfigInternal)
def get_ai_config_internal(request, company_id: str):
    """
    Fetch company AI config (embedding provider, model, LLM defaults).
    nexus-ai calls this to know which embedding provider to use.
    """
    from nucleus.models import CompanyAIConfig

    config = CompanyAIConfig.objects.filter(company__id=company_id).first()

    if not config:
        raise HttpError(404, "AI config not found for this company.")

    return AIConfigInternal(
        embedding_provider=config.embedding_provider,
        embedding_model=config.embedding_model,
        embedding_base_url=config.embedding_base_url,
        default_llm_model=config.default_llm_model,
    )
