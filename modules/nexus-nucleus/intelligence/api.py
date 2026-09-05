"""
AI Intelligence API — ModelConfig, MCPServer, Persona, PromptTemplate,
CompanyAIConfig. All endpoints require Supabase JWT auth and are
company-scoped.

── Removed in the AIAgent collapse ───────────────────────────────────────
Seven endpoints are gone:
    GET/POST/PATCH/DELETE  /agents/...
    GET/POST/DELETE        /ai-models/{id}/mcp-servers/...   (legacy nested)

The legacy nested POST had been returning 500 on every call -- it passed
project_id and client_secret into MCPServer(**data), which has neither
field -- and when it did work it created an AIAgent with no project
attached, invisible to everyone under row-level visibility.

/ai-models/ is now /model-configs/, and PATCH /model-configs/{id}/ is new:
rotating an API key used to require delete-and-recreate, and delete is
refused while any persona references the row.
"""
from typing import List
from ninja import Router
from ninja.errors import HttpError
from pathlib import Path
import base64
import binascii

from nucleus.models import Project, Persona, AIRequestLog
from authn.auth import SupabaseBearer
from authn.permissions.checker import PermissionChecker
from .schema import (
    ModelConfigIn, ModelConfigPatchIn, ModelConfigOut, ModelConfigRef,
    MCPServerIn, MCPServerPatchIn, MCPServerOut, MCPServerRef,
    MCPOAuthAuthorizeOut,
    PersonaIn, PersonaPatchIn, PersonaOut,
    PromptTemplateOut,
    CompanyAIConfigIn, CompanyAIConfigOut,
    AIRequestLogOut,
    ListTemplatePrompts,
    TemplatePromptContent,
)
from . import services as svc

router = Router(tags=["Intelligence"], auth=SupabaseBearer())

PROMPTS_DIR = (Path(__file__).resolve().parent / 'prompts').resolve()


def _company(request):
    company = svc.get_company()
    if not company:
        raise HttpError(503, "Server not initialised.")
    return company


# ── Serialisers ───────────────────────────────────────────────────────────────

def _oauth_connected(server) -> bool:
    """
    True iff a refresh token is stored. Only decrypts for oauth2 servers --
    get_secrets() is a Fernet decrypt, and doing it for every static-secrets
    server in a list would be pure waste.
    """
    if server.auth_type != "oauth2":
        return False
    return bool(server.get_secrets().get("refresh_token"))


def _model_config_out(config) -> ModelConfigOut:
    return ModelConfigOut(
        id=str(config.id),
        name=config.name,
        provider=config.provider,
        model_id=config.model_id,
        qualified_id=config.qualified_id,
        api_base=config.api_base,
        description=config.description,
        licence_accepted=config.licence_accepted,
        context_window=config.context_window,
        supports_tools=config.supports_tools,
        supports_streaming=config.supports_streaming,
        supports_vision=config.supports_vision,
        supports_audio=config.supports_audio,
        config=config.config,
        is_active=config.is_active,
        has_api_key=bool(config.api_key_encrypted),
        project_ids=[
            str(pid) for pid in config.projects.filter(is_active=True).values_list("id", flat=True)
        ],
    )


def _model_config_ref(config) -> ModelConfigRef:
    return ModelConfigRef(
        id=str(config.id),
        name=config.name,
        provider=config.provider,
        model_id=config.model_id,
        qualified_id=config.qualified_id,
        supports_tools=config.supports_tools,
    )


def _mcp_out(server) -> MCPServerOut:
    return MCPServerOut(
        id=str(server.id),
        name=server.name,
        description=server.description,
        project_id=str(server.project_id),
        server_type=server.server_type,
        transport=server.transport,
        url=server.url,
        command=server.command,
        docker_image=server.docker_image,
        config=server.config,
        timeout_seconds=server.timeout_seconds,
        max_retries=server.max_retries,
        is_first_party=server.is_first_party,
        embed_output=server.embed_output,
        is_active=server.is_active,
        auth_type=server.auth_type,
        oauth_connected=_oauth_connected(server),
        oauth_config=server.oauth_config,
    )


def _mcp_ref(server) -> MCPServerRef:
    return MCPServerRef(
        id=str(server.id),
        name=server.name,
        transport=server.transport,
        auth_type=server.auth_type,
        oauth_connected=_oauth_connected(server),
    )


def _persona_out(persona) -> PersonaOut:
    from .schema import PromptOut
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
        project_id=str(persona.project_id),
        model=_model_config_ref(persona.model),
        advisor_model=_model_config_ref(persona.advisor_model) if persona.advisor_model_id else None,
        mcp_servers=[_mcp_ref(s) for s in persona.mcp_servers.all() if s.is_active],
        temperature=persona.temperature,
        max_tokens=persona.max_tokens,
        max_steps=persona.max_steps,
        prompt=prompt,
        is_active=persona.is_active,
        avatar=(
            persona.identity_user.avatar.url
            if persona.identity_user_id and persona.identity_user.avatar
            else None
        ),
    )


# ── ModelConfig endpoints ─────────────────────────────────────────────────────
# Rights: model_config.list / .create / .update / .delete — COMPANY scope only
# (AI infrastructure has no project boundary). model_config.attach is PROJECT
# scope: attaching an existing config never touches its API key, so it is a
# lighter action reachable by that project's own Admin.

@router.get("/model-configs/", response=List[ModelConfigOut])
def list_model_configs(request):
    company = _company(request)
    return [_model_config_out(m) for m in svc.list_model_configs(company, request.auth)]


@router.post("/model-configs/", response=ModelConfigOut)
def create_model_config(request, payload: ModelConfigIn):
    company = _company(request)
    if not PermissionChecker.can(request.auth, "model_config.create", company=company):
        raise HttpError(403, "You don't have permission to create model configs.")
    if not payload.licence_accepted:
        raise HttpError(400, "You must accept the provider's terms of service.")
    try:
        config = svc.create_model_config(company, request.auth, payload.dict())
    except ValueError as e:
        raise HttpError(400, str(e))
    return _model_config_out(config)


@router.patch("/model-configs/{config_id}/", response=ModelConfigOut)
def patch_model_config(request, config_id: str, payload: ModelConfigPatchIn):
    company = _company(request)
    if not PermissionChecker.can(request.auth, "model_config.update", company=company):
        raise HttpError(403, "You don't have permission to edit model configs.")
    try:
        config = svc.update_model_config(company, config_id, payload.dict(exclude_none=True))
    except ValueError as e:
        raise HttpError(400, str(e))
    if not config:
        raise HttpError(404, "Model config not found.")
    return _model_config_out(config)


@router.delete("/model-configs/{config_id}/", response={204: None})
def delete_model_config(request, config_id: str):
    company = _company(request)
    if not PermissionChecker.can(request.auth, "model_config.delete", company=company):
        raise HttpError(403, "You don't have permission to delete model configs.")
    try:
        deleted = svc.delete_model_config(company, config_id)
    except ValueError as e:
        raise HttpError(409, str(e))
    if not deleted:
        raise HttpError(404, "Model config not found.")
    return 204, None


# ── ModelConfig <-> Project attachment (visibility gate) ──────────────────────

@router.post("/projects/{project_id}/model-configs/{config_id}/attach/", response={200: dict})
def attach_model_config(request, project_id: str, config_id: str):
    company = _company(request)
    project = Project.objects.filter(company=company, id=project_id, is_active=True).first()
    if not project:
        raise HttpError(404, "Project not found.")
    if not PermissionChecker.can(request.auth, "model_config.attach", obj=project):
        raise HttpError(403, "You don't have permission to attach model configs to this project.")
    if not svc.attach_model_config_to_project(company, config_id, project_id):
        raise HttpError(404, "Model config not found.")
    return {"ok": True}


@router.delete("/projects/{project_id}/model-configs/{config_id}/attach/", response={200: dict})
def detach_model_config(request, project_id: str, config_id: str):
    company = _company(request)
    project = Project.objects.filter(company=company, id=project_id, is_active=True).first()
    if not project:
        raise HttpError(404, "Project not found.")
    if not PermissionChecker.can(request.auth, "model_config.attach", obj=project):
        raise HttpError(403, "You don't have permission to detach model configs from this project.")
    try:
        detached = svc.detach_model_config_from_project(company, config_id, project_id)
    except ValueError as e:
        raise HttpError(409, str(e))
    if not detached:
        raise HttpError(404, "Model config not found.")
    return {"ok": True}


# ── MCPServer endpoints ───────────────────────────────────────────────────────
# mcp_server.list is COMPANY scope (ordinary project members reach the list
# through the visible_mcp_servers() row-visibility fallback, not by holding
# this right directly). create/update/delete are PROJECT scope — a server
# belongs to exactly one project, and that project's own Admin can manage it.

@router.get("/mcp-servers/", response=List[MCPServerOut])
def list_mcp_servers_all(request):
    company = _company(request)
    return [_mcp_out(s) for s in svc.list_mcp_servers_all(company, request.auth)]


@router.post("/mcp-servers/", response=MCPServerOut)
def create_mcp_server_standalone(request, payload: MCPServerIn):
    company = _company(request)
    project = Project.objects.filter(company=company, id=payload.project_id, is_active=True).first()
    if not project:
        raise HttpError(404, "Project not found.")
    if not PermissionChecker.can(request.auth, "mcp_server.create", obj=project):
        raise HttpError(403, "You don't have permission to create MCP servers in this project.")
    try:
        server = svc.create_mcp_server_standalone(company, payload.dict())
    except ValueError as e:
        raise HttpError(400, str(e))
    return _mcp_out(server)


@router.patch("/mcp-servers/{server_id}/", response=MCPServerOut)
def patch_mcp_server_standalone(request, server_id: str, payload: MCPServerPatchIn):
    company = _company(request)
    server = svc.get_mcp_server_standalone(company, server_id)
    if not server:
        raise HttpError(404, "MCP server not found.")
    if not PermissionChecker.can(request.auth, "mcp_server.update", obj=server):
        raise HttpError(403, "You don't have permission to edit this MCP server.")
    try:
        server = svc.update_mcp_server_standalone(company, server_id, payload.dict(exclude_none=True))
    except ValueError as e:
        raise HttpError(400, str(e))
    return _mcp_out(server)


@router.delete("/mcp-servers/{server_id}/", response={204: None})
def delete_mcp_server_standalone(request, server_id: str):
    company = _company(request)
    server = svc.get_mcp_server_standalone(company, server_id)
    if not server:
        raise HttpError(404, "MCP server not found.")
    if not PermissionChecker.can(request.auth, "mcp_server.delete", obj=server):
        raise HttpError(403, "You don't have permission to delete this MCP server.")
    try:
        svc.delete_mcp_server_standalone(company, server_id)
    except ValueError as e:
        raise HttpError(409, str(e))
    return 204, None


# MCPServer has no attach/detach endpoints -- it is single-project-owned via
# a real FK now, assigned once at creation via payload.project_id and not
# transferable. Unlike ModelConfig, which is genuinely shared across projects.


# ── MCPServer OAuth2 ───────────────────────────────────────────────────────────

@router.get("/mcp-servers/{server_id}/oauth/authorize/", response=MCPOAuthAuthorizeOut)
def mcp_oauth_authorize(request, server_id: str, frontend_origin: str):
    from nucleus.models import MCPServer
    from . import oauth_client

    company = _company(request)
    server = svc.get_mcp_server_standalone(company, server_id)
    if not server:
        raise HttpError(404, "MCP server not found.")
    if not PermissionChecker.can(request.auth, "mcp_server.update", obj=server):
        raise HttpError(403, "You don't have permission to connect this MCP server.")
    if server.auth_type != MCPServer.AuthType.OAUTH2:
        raise HttpError(400, "This MCP server is not configured for OAuth2.")
    return {"authorize_url": oauth_client.build_authorize_url(server, frontend_origin)}


@router.get("/mcp-servers/oauth/callback/", auth=None)
def mcp_oauth_callback(request, code: str = None, state: str = None, error: str = None):
    """
    Public -- the OAuth provider redirects the browser here directly, no
    Authorization header available. Returns a tiny self-closing HTML page
    that posts the result back to window.opener (standard OAuth popup
    pattern) -- there's no frontend route for this at all.
    """
    from django.core import signing
    from django.http import HttpResponse
    from . import oauth_client
    import json

    def html(ok: bool, origin: str | None, err: str = "", server_id: str = "") -> HttpResponse:
        payload = json.dumps({"type": "mcp-oauth-result", "ok": ok, "server_id": server_id, "error": err})
        target = json.dumps(origin) if origin else "'*'"
        body = "Connected. You can close this window." if ok else f"Connection failed: {err}"
        return HttpResponse(
            f"<!doctype html><html><body><script>"
            f"if (window.opener) {{ window.opener.postMessage({payload}, {target}); }}"
            f"window.close();</script>{body}</body></html>"
        )

    if error or not code or not state:
        return html(False, None, err=error or "missing_code")
    try:
        result = oauth_client.complete_callback(code, state)
    except (signing.BadSignature, ValueError) as exc:
        return html(False, None, err=str(exc))
    return html(True, result["frontend_origin"], server_id=result["server_id"])


# ── Persona endpoints ─────────────────────────────────────────────────────────
# persona.list is COMPANY scope; create/update/delete are PROJECT scope --
# a persona belongs to exactly one project and that project's own Admin
# manages it. Distinct from "persona.mention" (TOPIC-scoped, chat/api.py).

@router.get("/personas/", response=List[PersonaOut])
def list_personas(request, project_id: str):
    """
    Personas are project-owned -- always listed for one project, never
    company-wide. Visibility is via visible_personas().
    """
    company = _company(request)
    project = Project.objects.filter(company=company, id=project_id, is_active=True).first()
    if not project:
        raise HttpError(404, "Project not found.")
    return [_persona_out(p) for p in svc.list_personas(project, request.auth)]


@router.post("/personas/", response=PersonaOut)
def create_persona(request, payload: PersonaIn):
    company = _company(request)
    project = Project.objects.filter(company=company, id=payload.project_id, is_active=True).first()
    if not project:
        raise HttpError(404, "Project not found.")
    if not PermissionChecker.can(request.auth, "persona.create", obj=project):
        raise HttpError(403, "You don't have permission to create personas in this project.")
    try:
        persona = svc.create_persona(company, request.auth, payload.dict())
    except ValueError as e:
        raise HttpError(400, str(e))
    return _persona_out(persona)


@router.patch("/personas/{persona_id}/", response=PersonaOut)
def patch_persona(request, persona_id: str, payload: PersonaPatchIn):
    company = _company(request)
    persona_obj = Persona.objects.filter(
        company=company, id=persona_id, is_active=True
    ).select_related("project").first()
    if not persona_obj:
        raise HttpError(404, "Persona not found.")
    if not PermissionChecker.can(request.auth, "persona.update", obj=persona_obj.project):
        raise HttpError(403, "You don't have permission to edit this persona.")

    # exclude_none keeps `mcp_server_ids: []` (detach all) distinct from
    # "not sent", which is why clear_advisor exists as a separate flag --
    # a nullable FK has no equivalent distinct value.
    data = payload.dict(exclude_none=True)
    try:
        persona = svc.patch_persona(company, persona_id, data)
    except ValueError as e:
        raise HttpError(400, str(e))
    if not persona:
        raise HttpError(404, "Persona not found.")
    return _persona_out(persona)


@router.delete("/personas/{persona_id}/", response={204: None})
def delete_persona(request, persona_id: str):
    company = _company(request)
    persona_obj = Persona.objects.filter(
        company=company, id=persona_id, is_active=True
    ).select_related("project").first()
    if not persona_obj:
        raise HttpError(404, "Persona not found.")
    if not PermissionChecker.can(request.auth, "persona.delete", obj=persona_obj.project):
        raise HttpError(403, "You don't have permission to delete this persona.")

    svc.delete_persona(company, persona_id)
    return 204, None


# ── PromptTemplate endpoints ──────────────────────────────────────────────────

@router.get("/prompt-templates", response=ListTemplatePrompts)
def get_prompts(request):
    files = {
        base64.urlsafe_b64encode(rel_path.encode()).decode().rstrip('='): rel_path
        for f in PROMPTS_DIR.rglob('*') if f.is_file()
        for rel_path in [str(f.relative_to(PROMPTS_DIR))]
    }
    return ListTemplatePrompts(prompts=files)


@router.get("/prompt-templates/{id}", response=TemplatePromptContent)
def get_prompt(request, id: str):
    try:
        padding_needed = 4 - (len(id) % 4)
        padded_id = id + ("=" * padding_needed)

        rel_path_str = base64.urlsafe_b64decode(padded_id).decode()

        target_path = (PROMPTS_DIR / rel_path_str).resolve()

        if not target_path.is_relative_to(PROMPTS_DIR) or not target_path.is_file():
            raise HttpError(404, "File not found")

        return TemplatePromptContent(content=target_path.read_text(encoding="utf-8"))

    except (ValueError, binascii.Error, UnicodeDecodeError):
        raise HttpError(400, "Invalid file ID format")


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


@router.get("/ai-request-logs/", response=List[AIRequestLogOut])
def list_ai_request_logs(request):
    """Return the last 200 AI request logs, newest first."""
    company = _company(request)
    logs = (
        AIRequestLog.objects.filter(company=company)
        .order_by("-created_at")[:200]
    )
    return [
        AIRequestLogOut(
            id=str(log.id),
            job_id=log.job_id,
            msg_id=log.msg_id,
            persona_id=str(log.persona_id) if log.persona_id else None,
            model_id=log.model_id,
            provider=log.provider,
            prompt=log.prompt,
            response=log.response,
            prompt_tokens=log.prompt_tokens,
            completion_tokens=log.completion_tokens,
            latency_ms=log.latency_ms,
            status=log.status,
            error=log.error,
            created_at=log.created_at.isoformat(),
        )
        for log in logs
    ]


# ── Output Types (M7) ─────────────────────────────────────────────────────────

@router.get("/output-types/")
def list_output_types(request):
    """
    Return all available AI output types.
    Used by the frontend @mention picker to show output type directives.
    These match the types registered in nexus-ai/apps/output_types/types.py.
    """
    _company(request)  # auth check
    return [
        {"name": "text",     "label": "Text",      "icon": "align-left",    "render_as": "text"},
        {"name": "code",     "label": "Code",      "icon": "code-2",        "render_as": "code"},
        {"name": "chart",    "label": "Chart",     "icon": "bar-chart-2",   "render_as": "html"},
        {"name": "table",    "label": "Table",     "icon": "table",         "render_as": "html"},
        {"name": "diagram",  "label": "Diagram",   "icon": "git-branch",    "render_as": "html"},
        {"name": "form",     "label": "Form",      "icon": "clipboard-list","render_as": "html"},
        {"name": "html",     "label": "HTML Page", "icon": "globe",         "render_as": "html"},
        {"name": "terminal", "label": "Terminal",  "icon": "terminal",      "render_as": "terminal"},
    ]
