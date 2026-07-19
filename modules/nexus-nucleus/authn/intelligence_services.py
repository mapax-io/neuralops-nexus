"""
Business logic for AI Models, Personas, Prompts, and PromptTemplates.
All queries are scoped to company — safe for multi-tenant use.
"""
from django.contrib.auth import get_user_model

User = get_user_model()


def get_company():
    from nucleus.models import Company
    return Company.objects.filter(is_active=True).first()


# ── AIModel ───────────────────────────────────────────────────────────────────

def list_ai_models(company):
    from nucleus.models import AIModel
    return AIModel.objects.filter(company=company, is_active=True).order_by("name")


def get_ai_model(company, model_id: str):
    from nucleus.models import AIModel
    return AIModel.objects.filter(company=company, id=model_id, is_active=True).first()


def create_ai_model(company, user, data: dict) -> "AIModel":
    from nucleus.models import AIModel
    api_key = data.pop("api_key", None)
    model = AIModel(company=company, created_by=user, **data)
    if api_key:
        model.set_api_key(api_key)
    model.save()
    return model


def delete_ai_model(company, model_id: str) -> bool:
    from nucleus.models import AIModel
    model = AIModel.objects.filter(company=company, id=model_id, is_active=True).first()
    if not model:
        return False
    model.soft_delete()
    return True


# ── MCPServer ─────────────────────────────────────────────────────────────────

def list_mcp_servers(company, ai_model_id: str):
    from nucleus.models import MCPServer, AIAgent
    # MCPServer links to AIAgent which links to AIModel
    return MCPServer.objects.filter(
        company=company,
        agents__model__id=ai_model_id,
        is_active=True,
    ).distinct()


def create_mcp_server(company, ai_model_id: str, data: dict) -> "MCPServer":
    from nucleus.models import MCPServer, AIAgent, AIModel
    model = AIModel.objects.filter(company=company, id=ai_model_id, is_active=True).first()
    if not model:
        raise ValueError("AIModel not found")

    server = MCPServer.objects.create(company=company, **data)

    # Create or update the AIAgent that links model + this MCP server
    AIAgent.objects.create(
        company=company,
        name=f"{model.name} + {server.name}",
        agent_type="internal",
        model=model,
        mcp_server=server,
    )
    return server


def delete_mcp_server(company, ai_model_id: str, server_id: str) -> bool:
    from nucleus.models import MCPServer
    server = MCPServer.objects.filter(
        company=company,
        id=server_id,
        agents__model__id=ai_model_id,
        is_active=True,
    ).first()
    if not server:
        return False
    server.soft_delete()
    return True


# ── Persona ───────────────────────────────────────────────────────────────────

def list_personas(company):
    from nucleus.models import Persona
    return Persona.objects.filter(
        company=company, is_active=True
    ).select_related("prompt", "model", "agent").order_by("name")


def get_persona(company, persona_id: str):
    from nucleus.models import Persona
    return Persona.objects.filter(
        company=company, id=persona_id, is_active=True
    ).select_related("prompt", "model", "agent").first()


def create_persona(company, user, data: dict) -> "Persona":
    from nucleus.models import Persona, AIModel, AIAgent
    from nucleus.models import Prompt, PromptTemplate

    prompt_data = data.pop("prompt")
    model_id = data.pop("model_id", None)
    agent_id = data.pop("agent_id", None)

    # Resolve model or agent
    model = AIModel.objects.filter(company=company, id=model_id, is_active=True).first() if model_id else None
    agent = AIAgent.objects.filter(company=company, id=agent_id, is_active=True).first() if agent_id else None

    # Create shadow user for the persona
    shadow_user = User.objects.create(
        username=f"persona_{data['name'].lower().replace(' ', '_')}",
        user_type="persona",
        is_active=True,
    )

    persona = Persona.objects.create(
        company=company,
        created_by=user,
        identity_user=shadow_user,
        model=model,
        agent=agent,
        **data,
    )

    # Create prompt
    template_id = prompt_data.pop("template_id", None)
    template = PromptTemplate.objects.filter(
        company=company, id=template_id
    ).first() if template_id else None

    Prompt.objects.create(
        company=company,
        persona=persona,
        template=template,
        **prompt_data,
    )

    return persona


def patch_persona(company, persona_id: str, data: dict) -> "Persona | None":
    from nucleus.models import Persona, Prompt, PromptTemplate

    persona = Persona.objects.filter(
        company=company, id=persona_id, is_active=True
    ).select_related("prompt").first()
    if not persona:
        return None

    prompt_data = data.pop("prompt", None)

    for field, value in data.items():
        if value is not None:
            setattr(persona, field, value)
    persona.save()

    if prompt_data and hasattr(persona, "prompt"):
        template_id = prompt_data.pop("template_id", None)
        template = None
        if template_id:
            template = PromptTemplate.objects.filter(
                company=company, id=template_id
            ).first()
        for field, value in prompt_data.items():
            if value is not None:
                setattr(persona.prompt, field, value)
        if template:
            persona.prompt.template = template
        persona.prompt.save()

    return persona


def delete_persona(company, persona_id: str) -> bool:
    from nucleus.models import Persona
    persona = Persona.objects.filter(
        company=company, id=persona_id, is_active=True
    ).first()
    if not persona:
        return False
    persona.soft_delete()
    return True


# ── PromptTemplate ────────────────────────────────────────────────────────────

def list_prompt_templates(company):
    from nucleus.models import PromptTemplate
    return PromptTemplate.objects.filter(
        company=company, is_active=True
    ).order_by("-is_featured", "title")


# ── CompanyAIConfig ───────────────────────────────────────────────────────────

def get_ai_config(company):
    from nucleus.models import CompanyAIConfig
    config, _ = CompanyAIConfig.objects.get_or_create(company=company)
    return config


def update_ai_config(company, user, data: dict):
    from nucleus.models import CompanyAIConfig
    config, _ = CompanyAIConfig.objects.get_or_create(company=company)
    for field, value in data.items():
        setattr(config, field, value)
    config.updated_by = user
    config.save()
    return config
