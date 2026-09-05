"""
python manage.py test_agent_persona_flow [--wiring-only | --persona-only]

Closes out #111/#112 -- exercises the Persona service methods that never
got the same full pass the other resource types (Project, Channel, Topic,
ModelConfig, MCPServer) got during the earlier manual shell walkthrough.

── What the AIAgent removal changed here ─────────────────────────────────
The Agent half of this command is gone: AIAgent was deleted and Persona
absorbed it, so there is no create_agent/list_agents/update_agent/
delete_agent left to exercise. What used to be "an agent" is now a persona
wired to a tool-capable ModelConfig with one or more MCPServers mounted,
plus an optional advisor model -- so the first section builds exactly that
and asserts the wiring, which is the thing the old agent CRUD was really
standing in for.

Owner-level CRUD only for this first pass -- proving the service methods
themselves work correctly. Row-visibility (visible_personas for a
narrower-permissioned user) is a separate, bigger test that needs its own
fixture user + RoleAssignment setup -- left for later, not part of this.

Safe to re-run: every leftover from a previous run is hard-deleted up
front, because the uniqueness that matters here is at the DATABASE level
(uniq_model_config_name_per_company, uniq_mcp_server_name_per_project,
uniq_persona_name_per_project) and none of those constraints ignore
soft-deleted rows -- so a name freed only by soft delete would still
collide on the next run.
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from intelligence import services as isvc
from nucleus.models import Company, MCPServer, ModelConfig, Persona
from workspace import services as wsvc

User = get_user_model()

_MODEL_NAME = "ModelConfigFlowTest (tools)"
_ADVISOR_NAME = "ModelConfigFlowTest (advisor)"
_MCP_NAME = "MCPFlowTest"
_WIRED_PERSONA_NAME = "PersonaWithToolsFlowTest"
_PERSONA_NAME = "PersonaFlowTest"


class Command(BaseCommand):
    help = (
        "Exercise the persona-with-tools wiring (ModelConfig + MCPServer + "
        "advisor) and the Persona CRUD methods end-to-end (#111/#112)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--wiring-only", action="store_true",
                            help="Only run the persona-with-tools wiring test.")
        parser.add_argument("--persona-only", action="store_true",
                            help="Only run the Persona CRUD test.")

    def handle(self, *args, **options):
        run_all = not any([options["wiring_only"], options["persona_only"]])

        if run_all or options["wiring_only"]:
            self._section("Persona with tools (ModelConfig + MCPServer + advisor)")
            self.test_persona_with_tools()

        if run_all or options["persona_only"]:
            self._section("Persona CRUD")
            self.test_persona_crud()

    def _section(self, title):
        self.stdout.write("=" * 60)
        self.stdout.write(self.style.NOTICE(title))
        self.stdout.write("=" * 60)

    # ── Fixtures -- fetched, not recreated, so this is safe to re-run ─────────

    def get_fixtures(self):
        company = Company.objects.first()
        if not company:
            raise RuntimeError("No Company exists yet -- nothing to test against.")
        owner = company.owner
        project = wsvc.list_projects(company, owner).first()
        if not project:
            raise RuntimeError("No Project exists yet -- create one first.")
        return company, owner, project

    def make_model_config(self, company, owner, project, name, *, supports_tools):
        """
        A throwaway ModelConfig, attached to `project` so a persona in that
        project is allowed to use it (_validate_persona_wiring refuses an
        unattached one). CRUD tests never make a real LLM call, so a fake
        model_id and no API key are fine -- unlike test_chat_flow's.

        model_id is the BARE name: create_model_config rejects anything
        carrying a "provider/" or "provider:" prefix.
        """
        config = ModelConfig.objects.filter(company=company, name=name).first()
        if config is None:
            config = isvc.create_model_config(company, owner, {
                "name": name,
                "provider": "openai",
                "model_id": "gpt-flow-test",
                "supports_tools": supports_tools,
                "licence_accepted": True,
            })
        elif not config.is_active:
            config.restore()

        isvc.attach_model_config_to_project(company, str(config.id), str(project.id))
        return config

    def purge_leftovers(self, company, project, persona_names):
        """
        Hard-delete anything a previous run left behind, personas first so
        the ModelConfig FKs (on_delete=PROTECT) are free by the time the
        configs go. Soft deletes would not be enough -- see module docstring.
        """
        stale_personas = Persona.objects.filter(
            project=project, name__in=persona_names,
        ).select_related("identity_user")
        for stale in stale_personas:
            shadow = stale.identity_user
            stale.delete()
            if shadow:
                shadow.delete()

        MCPServer.objects.filter(project=project, name=_MCP_NAME).delete()

    # ── Persona with tools -- what an "agent" is now ─────────────────────────

    def test_persona_with_tools(self):
        company, owner, project = self.get_fixtures()
        self.purge_leftovers(company, project, [_WIRED_PERSONA_NAME])

        model = self.make_model_config(
            company, owner, project, _MODEL_NAME, supports_tools=True,
        )
        advisor = self.make_model_config(
            company, owner, project, _ADVISOR_NAME, supports_tools=False,
        )
        self.stdout.write(
            f"model config: {model.id} ({model.name}, qualified_id={model.qualified_id}, "
            f"supports_tools={model.supports_tools})"
        )
        self.stdout.write(f"advisor config: {advisor.id} ({advisor.name})")

        server = isvc.create_mcp_server_standalone(company, {
            "name": _MCP_NAME,
            "project_id": str(project.id),
            "server_type": "remote",
            "transport": "http",
            "url": "https://example.test/mcp-persona-flow",
        })
        self.stdout.write(
            f"create_mcp_server_standalone: {server.id} ({server.name}, "
            f"project={server.project.name})"
        )

        persona = isvc.create_persona(company, owner, {
            "name": _WIRED_PERSONA_NAME,
            "description": "Persona wired to a tool-capable model + one MCP server.",
            "project_id": str(project.id),
            "model_config_id": str(model.id),
            "advisor_model_config_id": str(advisor.id),
            "mcp_server_ids": [str(server.id)],
            "max_steps": 7,
            "prompt": {"system_prompt": "Test persona for #111/#112 wiring verification."},
        })
        self.stdout.write(f"create_persona: {persona.id} ({persona.name})")

        # The assertions the old agent CRUD test was really standing in for:
        # a persona IS the composition, so the wiring is the thing to check.
        mounted = list(persona.mcp_servers.all())
        checks = [
            ("model is the tool-capable config", persona.model_id == model.id),
            ("advisor is the second config", persona.advisor_model_id == advisor.id),
            ("advisor differs from primary", persona.advisor_model_id != persona.model_id),
            ("exactly one MCP server mounted", len(mounted) == 1),
            ("mounted server is the one created", bool(mounted) and mounted[0].id == server.id),
            ("mounted server is in the persona's project", bool(mounted) and mounted[0].project_id == persona.project_id),
            ("max_steps stored on the persona", persona.max_steps == 7),
            ("temperature defaulted on the persona", persona.temperature == 0.7),
        ]
        for label, ok in checks:
            style = self.style.SUCCESS if ok else self.style.ERROR
            self.stdout.write(style(f"  [{'OK' if ok else 'FAILED'}] {label}"))

        # A tool server cannot be deleted while a persona still mounts it,
        # and a config cannot be deleted while a persona still points at it
        # -- so the persona goes first. Both guards live in services.py.
        deleted_persona = isvc.delete_persona(company, str(persona.id))
        deleted_server = isvc.delete_mcp_server_standalone(company, str(server.id))
        deleted_advisor = isvc.delete_model_config(company, str(advisor.id))
        deleted_model = isvc.delete_model_config(company, str(model.id))
        self.stdout.write(
            f"cleanup: persona={deleted_persona}, mcp_server={deleted_server}, "
            f"advisor_config={deleted_advisor}, model_config={deleted_model}"
        )

    # ── Persona ──────────────────────────────────────────────────────────────

    def test_persona_crud(self):
        company, owner, project = self.get_fixtures()
        self.purge_leftovers(company, project, [_PERSONA_NAME])

        model = self.make_model_config(
            company, owner, project, _MODEL_NAME, supports_tools=True,
        )

        persona = isvc.create_persona(company, owner, {
            "name": _PERSONA_NAME,
            "model_config_id": str(model.id),
            "project_id": str(project.id),
            "prompt": {"system_prompt": "Test persona for #111/#112 CRUD verification."},
        })
        self.stdout.write(f"create_persona: {persona.id} ({persona.name}, model={persona.model.name})")

        listed = list(isvc.list_personas(project, owner))
        found = any(p.id == persona.id for p in listed)
        self.stdout.write(f"list_personas: {len(listed)} personas, created one present={found}")

        fetched = isvc.get_persona(company, str(persona.id))
        self.stdout.write(f"get_persona: {'OK' if fetched and fetched.id == persona.id else 'FAILED'}")

        patched = isvc.patch_persona(company, str(persona.id), {
            "description": "patched by test_agent_persona_flow",
            "temperature": 0.2,
            "prompt": {"system_prompt": "Updated system prompt."},
        })
        ok = (
            patched.description == "patched by test_agent_persona_flow"
            and patched.temperature == 0.2
            and patched.prompt.system_prompt == "Updated system prompt."
        )
        self.stdout.write(f"patch_persona: description+temperature+prompt updated ({'OK' if ok else 'FAILED'})")

        shadow_user_id = persona.identity_user_id
        deleted = isvc.delete_persona(company, str(persona.id))
        shadow_user = User.objects.filter(id=shadow_user_id).first()
        still_listed = any(p.id == persona.id for p in isvc.list_personas(project, owner))
        self.stdout.write(
            f"delete_persona: deleted={deleted}, shadow_user.is_active={shadow_user.is_active if shadow_user else None}, "
            f"still in list_personas={still_listed} "
            f"({'OK' if deleted and shadow_user and not shadow_user.is_active and not still_listed else 'FAILED'})"
        )

        # The config is left behind on purpose here -- delete_model_config
        # refuses while any active persona references it, and the CRUD test
        # above has already proved the persona is gone.
        self.stdout.write(f"model config left in place for re-runs: {model.name}")
