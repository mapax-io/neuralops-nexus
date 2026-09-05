"""
Business logic for ModelConfig, MCPServer, Personas, Prompts, and
PromptTemplates. All queries are scoped to company.

── What the AIAgent removal changed here ─────────────────────────────────
Eight functions are gone: the five agent CRUD functions, plus the three
legacy model-scoped MCP helpers (list_mcp_servers / create_mcp_server /
delete_mcp_server) that reached servers via `agents__model__id`. One of
them -- create_mcp_server -- had been raising TypeError on every call for
some time, because it passed project_id and client_secret straight into
MCPServer(**data) and neither is a field.

── Cross-object rules Django cannot enforce ──────────────────────────────
Three relationships need checking in Python because the database cannot
express them:

  * an MCP server attached to a persona must be in the persona's project
    (two FKs to Project, no way to constrain them against each other)
  * a model config used by a persona must be visible from that project
    (an M2M, and Django cannot constrain an auto through-table)
  * everything involved must belong to the same company

_validate_persona_wiring() is the single place all three are applied.
"""
from django.contrib.auth import get_user_model

User = get_user_model()

# Soft cap on tool servers per persona. Each one means a live MCP session
# per trigger and every one of its tools lands in the model's tool list, so
# an unbounded number bloats the prompt and slows the run. Not a database
# constraint -- a guard rail with a number we can revisit.
MAX_MCP_SERVERS_PER_PERSONA = 5


def get_company():
    from nucleus.models import Company
    return Company.objects.filter(is_active=True).first()


# ── ModelConfig ───────────────────────────────────────────────────────────────

def list_model_configs(company, user):
    from authn.permissions.row_rules import visible_model_configs
    return visible_model_configs(user, company)


def get_model_config(company, config_id: str):
    from nucleus.models import ModelConfig
    return ModelConfig.objects.filter(
        company=company, id=config_id, is_active=True
    ).first()


def create_model_config(company, user, data: dict):
    from nucleus.models import ModelConfig

    api_key = data.pop("api_key", None)
    _reject_prefixed_model_id(data.get("model_id"))

    config = ModelConfig(company=company, created_by=user, **data)
    if api_key:
        config.set_api_key(api_key)
    config.save()
    return config


def update_model_config(company, config_id: str, data: dict):
    """
    Backs PATCH /model-configs/{id}/, which did not exist before: rotating a
    key used to mean delete-and-recreate, and delete is blocked by any
    persona using the row.

    provider and model_id are not patchable -- see ModelConfigPatchIn.
    """
    config = get_model_config(company, config_id)
    if not config:
        return None

    api_key = data.pop("api_key", None)
    data.pop("provider", None)
    data.pop("model_id", None)

    for field, value in data.items():
        if value is not None:
            setattr(config, field, value)
    if api_key:
        config.set_api_key(api_key)
    config.save()
    return config


def attach_model_config_to_project(company, config_id: str, project_id: str) -> bool:
    from nucleus.models import ModelConfig, Project
    config = ModelConfig.objects.filter(company=company, id=config_id, is_active=True).first()
    project = Project.objects.filter(company=company, id=project_id, is_active=True).first()
    if not config or not project:
        return False
    config.projects.add(project)
    return True


def detach_model_config_from_project(company, config_id: str, project_id: str) -> bool:
    """
    Refuses while a persona in that project still uses the config, as either
    its primary or its advisor -- detaching would leave a persona pointing at
    a model it can no longer see.
    """
    from nucleus.models import ModelConfig, Persona
    from django.db.models import Q

    config = ModelConfig.objects.filter(company=company, id=config_id, is_active=True).first()
    if not config:
        return False

    in_use = Persona.objects.filter(
        Q(model_id=config.id) | Q(advisor_model_id=config.id),
        project_id=project_id,
        is_active=True,
    ).values_list("name", flat=True)
    if in_use:
        raise ValueError(
            "Cannot detach '%s' from this project -- still used by: %s."
            % (config.name, ", ".join(in_use))
        )

    config.projects.remove(project_id)
    return True


def delete_model_config(company, config_id: str) -> bool:
    """
    Refuses while any active persona references this config.

    on_delete=PROTECT does nothing here: every delete in this codebase is a
    soft delete (is_active=False), so the database-level protection never
    fires and an active persona can end up pointing at a deleted model. This
    check is the actual guard.
    """
    from nucleus.models import ModelConfig, Persona
    from django.db.models import Q

    config = ModelConfig.objects.filter(company=company, id=config_id, is_active=True).first()
    if not config:
        return False

    in_use = list(
        Persona.objects.filter(
            Q(model_id=config.id) | Q(advisor_model_id=config.id), is_active=True
        ).values_list("name", flat=True)
    )
    if in_use:
        raise ValueError(
            "Cannot delete '%s' -- still used by persona(s): %s. Repoint or "
            "delete them first." % (config.name, ", ".join(in_use))
        )

    config.soft_delete()
    return True


def _reject_prefixed_model_id(model_id) -> None:
    """
    model_id holds the BARE model name. A value carrying a provider prefix
    is almost always someone pasting a LiteLLM ("anthropic/claude-...") or
    pydantic-ai ("anthropic:claude-...") string, which would make
    qualified_id produce "openai:anthropic/claude-..." and fail at call time
    with a confusing provider error.
    """
    value = (model_id or "").strip()
    if "/" in value or ":" in value:
        raise ValueError(
            "model_id must be the bare model name without a provider prefix "
            "(e.g. 'gpt-4o', not 'openai/gpt-4o'). Set the provider field "
            "separately."
        )


# ── MCPServer ─────────────────────────────────────────────────────────────────

def list_mcp_servers_all(company, user):
    """Every MCP server visible to this user."""
    from authn.permissions.row_rules import visible_mcp_servers
    return visible_mcp_servers(user, company)


def create_mcp_server_standalone(company, data: dict):
    """
    MCP servers are project-owned via a real FK now, so the per-project name
    collision check that used to live here is a database constraint
    (uniq_mcp_server_name_per_project) and has been removed.
    """
    from nucleus.models import MCPServer, Project
    from django.db import IntegrityError

    project_id = data.pop("project_id")
    client_secret = data.pop("client_secret", None)

    project = Project.objects.filter(company=company, id=project_id, is_active=True).first()
    if not project:
        raise ValueError("Project not found.")

    try:
        server = MCPServer.objects.create(company=company, project=project, **data)
    except IntegrityError:
        raise ValueError(
            "An MCP server named '%s' already exists in this project."
            % data.get("name")
        )

    if client_secret:
        server.set_secrets({**server.get_secrets(), "client_secret": client_secret})
        server.save()
    return server


def get_mcp_server_standalone(company, server_id: str):
    from nucleus.models import MCPServer
    return MCPServer.objects.filter(
        company=company, id=server_id, is_active=True
    ).select_related("project").first()


def update_mcp_server_standalone(company, server_id: str, data: dict):
    """
    Company scoping is applied by get_mcp_server_standalone() above, so the
    setattr loop can only ever touch a row this company owns -- the previous
    version fetched without that guard.
    """
    server = get_mcp_server_standalone(company, server_id)
    if not server:
        return None

    client_secret = data.pop("client_secret", None)
    data.pop("project_id", None)      # ownership is fixed at creation
    data.pop("project", None)

    for field, value in data.items():
        if value is not None:
            setattr(server, field, value)
    if client_secret:
        server.set_secrets({**server.get_secrets(), "client_secret": client_secret})
    server.save()
    return server


def delete_mcp_server_standalone(company, server_id: str) -> bool:
    """
    Refuses while any active persona mounts this server -- same reasoning as
    delete_model_config: soft deletes mean PROTECT never fires.
    """
    from nucleus.models import MCPServer

    server = MCPServer.objects.filter(
        company=company, id=server_id, is_active=True
    ).first()
    if not server:
        return False

    in_use = list(server.personas.filter(is_active=True).values_list("name", flat=True))
    if in_use:
        raise ValueError(
            "Cannot delete '%s' -- still mounted by persona(s): %s. Detach it "
            "there first." % (server.name, ", ".join(in_use))
        )

    server.soft_delete()
    return True


# ── Persona ───────────────────────────────────────────────────────────────────

def _validate_persona_wiring(company, project, model_config, advisor, servers):
    """
    Every cross-object rule the database cannot express, in one place.
    Raises ValueError, which the API layer turns into a 400.
    """
    if model_config is None:
        raise ValueError("A model config is required.")

    for label, config in (("model", model_config), ("advisor model", advisor)):
        if config is None:
            continue
        if config.company_id != company.id:
            raise ValueError("The chosen %s belongs to a different company." % label)
        if not config.projects.filter(id=project.id).exists():
            raise ValueError(
                "The chosen %s ('%s') is not attached to this project. Attach "
                "it first." % (label, config.name)
            )

    if advisor is not None and advisor.id == model_config.id:
        raise ValueError(
            "The advisor must be a different model from the primary -- "
            "otherwise it just asks the same model twice."
        )

    if servers:
        if len(servers) > MAX_MCP_SERVERS_PER_PERSONA:
            raise ValueError(
                "A persona can mount at most %d MCP servers."
                % MAX_MCP_SERVERS_PER_PERSONA
            )
        if not model_config.supports_tools:
            raise ValueError(
                "'%s' is not marked as tool-capable, so MCP servers cannot be "
                "attached to a persona using it. Enable supports_tools on the "
                "model config, or pick a different one." % model_config.name
            )
        stray = [s.name for s in servers if s.project_id != project.id]
        if stray:
            raise ValueError(
                "These MCP servers belong to a different project: %s. Servers "
                "are not transferable between projects." % ", ".join(stray)
            )


def _resolve_model_config(company, config_id):
    from nucleus.models import ModelConfig
    if not config_id:
        return None
    config = ModelConfig.objects.filter(
        company=company, id=config_id, is_active=True
    ).first()
    if config is None:
        raise ValueError("Model config not found.")
    return config


def _resolve_mcp_servers(company, server_ids):
    from nucleus.models import MCPServer
    ids = list(dict.fromkeys(server_ids or []))
    if not ids:
        return []
    servers = list(MCPServer.objects.filter(company=company, id__in=ids, is_active=True))
    if len(servers) != len(ids):
        raise ValueError("One or more MCP servers were not found.")
    return servers


def get_persona_by_mention(project, mention_name: str):
    """
    Look up a Persona by @mention name (case-insensitive), scoped to a single
    project -- personas are project-owned and not mentionable from any other
    project. Used by chat/api.py to detect @PersonaName in messages.
    """
    from nucleus.models import Persona
    return (
        Persona.objects.filter(project=project, is_active=True)
        .select_related("prompt", "model", "advisor_model", "identity_user")
        .prefetch_related("mcp_servers")
        .filter(name__iexact=mention_name)
        .first()
    )


def list_personas(project, user):
    from authn.permissions.row_rules import visible_personas
    return (
        visible_personas(user, project)
        .select_related("prompt", "model", "advisor_model", "identity_user")
        .prefetch_related("mcp_servers")
    )


def get_persona(company, persona_id: str):
    from nucleus.models import Persona
    return (
        Persona.objects.filter(company=company, id=persona_id, is_active=True)
        .select_related("prompt", "model", "advisor_model", "identity_user", "project")
        .prefetch_related("mcp_servers")
        .first()
    )


def create_persona(company, user, data: dict):
    from nucleus.models import Persona, Project, Prompt, PromptTemplate

    prompt_data = data.pop("prompt")
    project_id = data.pop("project_id")
    model_config_id = data.pop("model_config_id", None)
    advisor_id = data.pop("advisor_model_config_id", None)
    server_ids = data.pop("mcp_server_ids", None)

    project = Project.objects.filter(company=company, id=project_id, is_active=True).first()
    if not project:
        raise ValueError("Project not found.")

    model_config = _resolve_model_config(company, model_config_id)
    advisor = _resolve_model_config(company, advisor_id)
    servers = _resolve_mcp_servers(company, server_ids)
    _validate_persona_wiring(company, project, model_config, advisor, servers)

    if Persona.objects.filter(project=project, name=data.get("name"), is_active=True).exists():
        raise ValueError(
            "A persona named '%s' already exists in this project." % data.get("name")
        )

    # Shadow user -- a persona is "the same as a User, just model-backed".
    base_username = "persona_%s" % data["name"].lower().replace(" ", "_")
    username, n = base_username, 1
    while User.objects.filter(username=username).exists():
        username = "%s_%d" % (base_username, n)
        n += 1
    shadow_user = User.objects.create(
        username=username, user_type="persona", is_active=True
    )
    from authn.services import assign_avatar
    assign_avatar(shadow_user)

    persona = Persona.objects.create(
        company=company,
        project=project,
        created_by=user,
        identity_user=shadow_user,
        model=model_config,
        advisor_model=advisor,
        **data,
    )
    if servers:
        persona.mcp_servers.set(servers)

    template_id = prompt_data.pop("template_id", None)
    template = PromptTemplate.objects.filter(
        company=company, id=template_id
    ).first() if template_id else None

    Prompt.objects.create(
        company=company, persona=persona, template=template, **prompt_data
    )

    return persona


def patch_persona(company, persona_id: str, data: dict):
    """
    The backing is mutable now -- DECISIONS.md §18 said it was not, which
    stopped being true when AIAgent went away.

    mcp_server_ids MUST be popped before the setattr loop: assigning to the
    forward side of a ManyToMany raises
        TypeError: Direct assignment to the forward side of a many-to-many
                   set is prohibited. Use mcp_servers.set() instead.
    """
    from nucleus.models import Persona, PromptTemplate

    persona = (
        Persona.objects.filter(company=company, id=persona_id, is_active=True)
        .select_related("prompt", "project", "model", "advisor_model")
        .first()
    )
    if not persona:
        return None

    prompt_data = data.pop("prompt", None)
    model_config_id = data.pop("model_config_id", None)
    advisor_id = data.pop("advisor_model_config_id", None)
    clear_advisor = data.pop("clear_advisor", False)
    server_ids = data.pop("mcp_server_ids", None)

    model_config = (
        _resolve_model_config(company, model_config_id) if model_config_id else persona.model
    )
    if clear_advisor:
        advisor = None
    elif advisor_id:
        advisor = _resolve_model_config(company, advisor_id)
    else:
        advisor = persona.advisor_model

    servers = (
        _resolve_mcp_servers(company, server_ids)
        if server_ids is not None
        else list(persona.mcp_servers.filter(is_active=True))
    )

    _validate_persona_wiring(company, persona.project, model_config, advisor, servers)

    persona.model = model_config
    persona.advisor_model = advisor
    for field, value in data.items():
        if value is not None:
            setattr(persona, field, value)
    persona.save()

    if server_ids is not None:
        persona.mcp_servers.set(servers)

    if prompt_data and hasattr(persona, "prompt"):
        template_id = prompt_data.pop("template_id", None)
        if template_id:
            template = PromptTemplate.objects.filter(company=company, id=template_id).first()
            if template:
                persona.prompt.template = template
        for field, value in prompt_data.items():
            if value is not None:
                setattr(persona.prompt, field, value)
        persona.prompt.save()

    return persona


def delete_persona(company, persona_id: str) -> bool:
    from nucleus.models import Persona
    import uuid

    persona = Persona.objects.filter(
        company=company, id=persona_id, is_active=True
    ).select_related("identity_user").first()
    if not persona:
        return False

    # Free the name + username so the same persona can be re-created later.
    suffix = uuid.uuid4().hex[:8]
    persona.name = "%s_deleted_%s" % (persona.name, suffix)
    persona.save(update_fields=["name"])
    if persona.identity_user:
        persona.identity_user.username = "deleted_%s" % suffix
        persona.identity_user.is_active = False
        persona.identity_user.save(update_fields=["username", "is_active"])
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
