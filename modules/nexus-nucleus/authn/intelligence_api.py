"""
AI Intelligence API — AIModel, MCPServer, Persona, PromptTemplate, CompanyAIConfig.
All endpoints require Supabase JWT auth and are company-scoped.
"""
from typing import List
from ninja import Router
from ninja.errors import HttpError

from .auth import SupabaseBearer
from .intelligence_schema import (
    AIModelIn, AIModelOut,
    MCPServerIn, MCPServerOut,
    PersonaIn, PersonaPatchIn, PersonaOut,
    PromptTemplateOut,
    CompanyAIConfigIn, CompanyAIConfigOut,
)
from . import intelligence_services as svc

router = Router(tags=["Intelligence"], auth=SupabaseBearer())


def _company(request):
    company = svc.get_company()
    if not company:
        raise HttpError(503, "Server not initialised.")
    return company


def _model_out(model) -> AIModelOut:
    return AIModelOut(
        id=str(model.id),
        name=model.name,
        provider=model.provider,
        model_id=model.model_id,
        api_base=model.api_base,
        secret_ref=model.secret_ref,
        description=model.description,
        licence_accepted=model.licence_accepted,
        temperature=model.temperature,
        max_tokens=model.max_tokens,
        context_window=model.context_window,
        supports_tools=model.supports_tools,
        supports_streaming=model.supports_streaming,
        supports_vision=model.supports_vision,
        supports_audio=model.supports_audio,
        config=model.config,
        is_active=model.is_active,
        has_api_key=bool(model.api_key_encrypted),
    )


def _mcp_out(server) -> MCPServerOut:
    return MCPServerOut(
        id=str(server.id),
        name=server.name,
        description=server.description,
        server_type=server.server_type,
        transport=server.transport,
        url=server.url,
        command=server.command,
        docker_image=server.docker_image,
        config=server.config,
        timeout_seconds=server.timeout_seconds,
        max_retries=server.max_retries,
        is_active=server.is_active,
    )


def _persona_out(persona) -> PersonaOut:
    from .intelligence_schema import PromptOut
    prompt = None
    if hasattr(persona, "prompt") and persona.prompt:
        p = persona.prompt
        prompt = PromptOut(
            id=str(p.id),
            system_prompt=p.system_prompt,
            output_type=p.output_type,
            context_scope=p.context_scope,
            template_id=str(p.template_id) if p.template_id else None,
        )
    return PersonaOut(
        id=str(persona.id),
        name=persona.name,
        description=persona.description,
        source_type=persona.source_type,
        model_id=str(persona.model_id) if persona.model_id else None,
        agent_id=str(persona.agent_id) if persona.agent_id else None,
        prompt=prompt,
        is_active=persona.is_active,
    )


# ── AIModel endpoints ─────────────────────────────────────────────────────────

@router.get("/ai-models/", response=List[AIModelOut])
def list_ai_models(request):
    company = _company(request)
    return [_model_out(m) for m in svc.list_ai_models(company)]


@router.post("/ai-models/", response=AIModelOut)
def create_ai_model(request, payload: AIModelIn):
    company = _company(request)
    if not payload.licence_accepted:
        raise HttpError(400, "You must accept the provider's terms of service.")
    data = payload.dict()
    model = svc.create_ai_model(company, request.auth, data)
    return _model_out(model)


@router.delete("/ai-models/{model_id}/", response={204: None})
def delete_ai_model(request, model_id: str):
    company = _company(request)
    if not svc.delete_ai_model(company, model_id):
        raise HttpError(404, "AI model not found.")
    return 204, None


# ── MCPServer endpoints ───────────────────────────────────────────────────────

@router.get("/ai-models/{model_id}/mcp-servers/", response=List[MCPServerOut])
def list_mcp_servers(request, model_id: str):
    company = _company(request)
    return [_mcp_out(s) for s in svc.list_mcp_servers(company, model_id)]


@router.post("/ai-models/{model_id}/mcp-servers/", response=MCPServerOut)
def create_mcp_server(request, model_id: str, payload: MCPServerIn):
    company = _company(request)
    try:
        server = svc.create_mcp_server(company, model_id, payload.dict())
    except ValueError as e:
        raise HttpError(404, str(e))
    return _mcp_out(server)


@router.delete("/ai-models/{model_id}/mcp-servers/{server_id}/", response={204: None})
def delete_mcp_server(request, model_id: str, server_id: str):
    company = _company(request)
    if not svc.delete_mcp_server(company, model_id, server_id):
        raise HttpError(404, "MCP server not found.")
    return 204, None


# ── Persona endpoints ─────────────────────────────────────────────────────────

@router.get("/personas/", response=List[PersonaOut])
def list_personas(request):
    company = _company(request)
    return [_persona_out(p) for p in svc.list_personas(company)]


@router.post("/personas/", response=PersonaOut)
def create_persona(request, payload: PersonaIn):
    company = _company(request)
    persona = svc.create_persona(company, request.auth, payload.dict())
    return _persona_out(persona)


@router.patch("/personas/{persona_id}/", response=PersonaOut)
def patch_persona(request, persona_id: str, payload: PersonaPatchIn):
    company = _company(request)
    persona = svc.patch_persona(company, persona_id, payload.dict(exclude_none=True))
    if not persona:
        raise HttpError(404, "Persona not found.")
    return _persona_out(persona)


@router.delete("/personas/{persona_id}/", response={204: None})
def delete_persona(request, persona_id: str):
    company = _company(request)
    if not svc.delete_persona(company, persona_id):
        raise HttpError(404, "Persona not found.")
    return 204, None


# ── PromptTemplate endpoints ──────────────────────────────────────────────────

@router.get("/prompt-templates/", response=List[PromptTemplateOut])
def list_prompt_templates(request):
    company = _company(request)
    return [
        PromptTemplateOut(
            id=str(t.id),
            title=t.title,
            description=t.description,
            system_prompt=t.system_prompt,
            output_type=t.output_type,
            tags=t.tags,
            is_featured=t.is_featured,
        )
        for t in svc.list_prompt_templates(company)
    ]


# ── CompanyAIConfig endpoints ─────────────────────────────────────────────────

@router.get("/ai-config/", response=CompanyAIConfigOut)
def get_ai_config(request):
    company = _company(request)
    config = svc.get_ai_config(company)
    return CompanyAIConfigOut(
        embedding_provider=config.embedding_provider,
        embedding_model=config.embedding_model,
        embedding_base_url=config.embedding_base_url,
        default_llm_model=config.default_llm_model,
    )


@router.put("/ai-config/", response=CompanyAIConfigOut)
def update_ai_config(request, payload: CompanyAIConfigIn):
    company = _company(request)
    config = svc.update_ai_config(company, request.auth, payload.dict())
    return CompanyAIConfigOut(
        embedding_provider=config.embedding_provider,
        embedding_model=config.embedding_model,
        embedding_base_url=config.embedding_base_url,
        default_llm_model=config.default_llm_model,
    )
