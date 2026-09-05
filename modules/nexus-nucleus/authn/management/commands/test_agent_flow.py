"""
Management command: python manage.py test_agent_flow

Exercises the lifecycle of the two resources that replaced AIAgent --
create -> list -> patch -> delete -- plus the RBAC rights checks around
each step, in one run.

── What the AIAgent removal changed here ─────────────────────────────────
There is no agent.create/agent.update/agent.delete/agent.list any more:
AIAgent is deleted, its Right rows are dropped in authn/migrations/0005,
and PermissionChecker.can() raises ValueError on an unregistered code, so
every check in this command had to be repointed. "An agent" is now a
persona mounting one or more MCP servers, and the rights that replaced the
agent.* set are:

    persona.create / persona.update / persona.delete       (PROJECT scope)
    mcp_server.create / mcp_server.update / mcp_server.delete (PROJECT scope)

Both families behave the way agent.* used to: a Project Admin on the
resource's own project reaches them with no company-wide role at all (see
USE_CASES.md UC16). persona.list and mcp_server.list stay COMPANY scope for
the blanket check, while ordinary project members still see their own
project's rows through the visible_personas()/visible_mcp_servers()
row-visibility fallback -- same "list never just 403s" pattern as
everywhere else.

This command also proves project-to-project isolation (UC17): a second
Project Admin, scoped to a DIFFERENT project, is denied on every check
against these rows, since _scope_chain() only reaches through the
resource's own project.
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from authn.permissions.checker import PermissionChecker
from authn.permissions.models import Role
from intelligence import services as isvc
from nucleus.models import Company, MCPServer, ModelConfig, Persona, Project

User = get_user_model()

_MODEL_NAME = "Test Model for Agent Flow"
_MCP_NAME = "Scout MCP Test Flow"
_PERSONA_NAME = "Scout Test Flow"


class Command(BaseCommand):
    help = (
        "Exercise the MCPServer + Persona CRUD lifecycle (what AIAgent became) "
        "+ rights checks in one run."
    )

    def handle(self, *args, **options):
        self._line()
        self.stdout.write(self.style.NOTICE(
            "Persona-with-tools lifecycle test (create -> list -> patch -> delete)"
        ))
        self._line()

        # ── Fixtures ─────────────────────────────────────────────────────────
        company = Company.objects.filter(is_active=True).first()
        if not company:
            self.stdout.write(self.style.ERROR("No company found -- run 'manage.py create_owner' first."))
            return
        owner = company.owner

        project = Project.objects.filter(company=company, is_active=True).first()
        if not project:
            self.stdout.write(self.style.ERROR("No active project found -- create one first (wsvc.create_project)."))
            return

        other_project, _ = Project.objects.get_or_create(
            company=company, slug="other-project-agent-flow",
            defaults={"name": "Other Project (agent flow isolation test)"},
        )

        # A tool-capable ModelConfig, attached to `project` -- a persona may
        # only mount MCP servers on a model marked supports_tools, and may
        # only use a config attached to its own project (both enforced in
        # intelligence/services.py:_validate_persona_wiring).
        model = ModelConfig.objects.filter(company=company, name=_MODEL_NAME).first()
        if model is None:
            self.stdout.write("No throwaway ModelConfig found -- creating one for this test.")
            model = isvc.create_model_config(company, owner, {
                "name": _MODEL_NAME, "provider": "openai", "model_id": "gpt-test",
                "supports_tools": True, "licence_accepted": True,
            })
        elif not model.is_active:
            model.restore()
        isvc.attach_model_config_to_project(company, str(model.id), str(project.id))

        # Hard-delete leftovers from a previous run: the uniqueness
        # constraints (uniq_mcp_server_name_per_project,
        # uniq_persona_name_per_project) do not ignore soft-deleted rows, so
        # a name freed only by this command's own delete step would still
        # collide here. Personas go first -- MCPServer/ModelConfig are still
        # referenced until they do.
        for stale in Persona.objects.filter(project=project, name=_PERSONA_NAME).select_related("identity_user"):
            shadow = stale.identity_user
            stale.delete()
            if shadow:
                shadow.delete()
        MCPServer.objects.filter(project=project, name=_MCP_NAME).delete()

        self.stdout.write(f"Company: {company.name} | Owner: {owner.email} | "
                          f"Project: {project.name} | Other project: {other_project.name} | Model: {model.name}")

        admin_role = Role.objects.filter(company=company, name="Admin").first()

        # Project Admin on `project` ONLY -- expect this user to reach every
        # persona.*/mcp_server.* write right on THIS project's rows, no
        # company-wide role needed.
        project_admin, created = User.objects.get_or_create(
            username="test_project_admin_agent_flow",
            defaults={"email": "test_project_admin_agent_flow@test.local", "user_type": "human"},
        )
        if admin_role:
            PermissionChecker.assign_role(project_admin, admin_role, project, granted_by=owner)
        self.stdout.write(f"Test user 1: {project_admin.username} (Project Admin on '{project.name}' only) "
                          f"{'[created]' if created else '[reused]'}")

        # Project Admin on a DIFFERENT project -- expect every check below to
        # be denied for this user, proving project-to-project isolation.
        other_admin, created2 = User.objects.get_or_create(
            username="test_other_project_admin_agent_flow",
            defaults={"email": "test_other_project_admin_agent_flow@test.local", "user_type": "human"},
        )
        if admin_role:
            PermissionChecker.assign_role(other_admin, admin_role, other_project, granted_by=owner)
        self.stdout.write(f"Test user 2: {other_admin.username} (Project Admin on '{other_project.name}' only) "
                          f"{'[created]' if created2 else '[reused]'}")

        # ── 1. mcp_server.create + persona.create ────────────────────────────
        self._section("1. CREATE -- mcp_server.create / persona.create (PROJECT scope, obj=project)")
        self._check("owner can mcp_server.create on project", PermissionChecker.can(owner, "mcp_server.create", obj=project), True)
        self._check("project_admin can mcp_server.create on project (own project)", PermissionChecker.can(project_admin, "mcp_server.create", obj=project), True)
        self._check("other_admin can mcp_server.create on project (different project)", PermissionChecker.can(other_admin, "mcp_server.create", obj=project), False)
        self._check("owner can persona.create on project", PermissionChecker.can(owner, "persona.create", obj=project), True)
        self._check("project_admin can persona.create on project (own project)", PermissionChecker.can(project_admin, "persona.create", obj=project), True)
        self._check("other_admin can persona.create on project (different project)", PermissionChecker.can(other_admin, "persona.create", obj=project), False)

        server = isvc.create_mcp_server_standalone(company, {
            "name": _MCP_NAME,
            "description": "Created by test_agent_flow management command.",
            "project_id": str(project.id),
            "server_type": "remote",
            "transport": "http",
            "url": "https://example.test/agent-flow",
        })
        self.stdout.write(f"  -> mcp server created: id={server.id} name={server.name!r} is_active={server.is_active}")

        persona = isvc.create_persona(company, owner, {
            "name": _PERSONA_NAME,
            "description": "Created by test_agent_flow management command.",
            "project_id": str(project.id),
            "model_config_id": str(model.id),
            "mcp_server_ids": [str(server.id)],
            "prompt": {"system_prompt": "You are Scout, a test persona with tools."},
        })
        self.stdout.write(f"  -> persona created: id={persona.id} name={persona.name!r} "
                          f"mcp_servers={[s.name for s in persona.mcp_servers.all()]}")

        # ── 2. *.list / row-visibility ───────────────────────────────────────
        self._section("2. LIST -- persona.list / mcp_server.list (blanket, company-wide) vs the visible_*() row rules")
        self._check("owner can persona.list (company-wide)", PermissionChecker.can(owner, "persona.list", company=company), True)
        self._check("project_admin can persona.list (company-wide)", PermissionChecker.can(project_admin, "persona.list", company=company), False)
        self._check("owner can mcp_server.list (company-wide)", PermissionChecker.can(owner, "mcp_server.list", company=company), True)
        self._check("project_admin can mcp_server.list (company-wide)", PermissionChecker.can(project_admin, "mcp_server.list", company=company), False)

        owner_sees = [p.name for p in isvc.list_personas(project, owner)]
        admin_sees = [p.name for p in isvc.list_personas(project, project_admin)]
        other_admin_sees = [s.name for s in isvc.list_mcp_servers_all(company, other_admin)]
        self.stdout.write(f"  -> owner's list_personas: {owner_sees}")
        self.stdout.write(f"  -> project_admin's list_personas (expect to still see it -- narrow-path reach): {admin_sees}")
        self.stdout.write(f"  -> other_admin's list_mcp_servers_all (expect NOT to see it -- different project): {other_admin_sees}")

        # ── 3. persona.update / mcp_server.update ────────────────────────────
        self._section("3. PATCH -- persona.update (obj=project) / mcp_server.update (obj=server, via the project FK)")
        self._check("owner can persona.update", PermissionChecker.can(owner, "persona.update", obj=project), True)
        self._check("project_admin can persona.update (own project's persona)", PermissionChecker.can(project_admin, "persona.update", obj=project), True)
        self._check("other_admin can persona.update on this project (different project)", PermissionChecker.can(other_admin, "persona.update", obj=project), False)
        self._check("owner can mcp_server.update", PermissionChecker.can(owner, "mcp_server.update", obj=server), True)
        self._check("project_admin can mcp_server.update (own project's server)", PermissionChecker.can(project_admin, "mcp_server.update", obj=server), True)
        self._check("other_admin can mcp_server.update (different project)", PermissionChecker.can(other_admin, "mcp_server.update", obj=server), False)

        updated = isvc.patch_persona(company, str(persona.id), {"description": "Updated by test_agent_flow."})
        self.stdout.write(f"  -> patched persona description: {updated.description!r}")
        updated_server = isvc.update_mcp_server_standalone(company, str(server.id), {"description": "Updated by test_agent_flow."})
        self.stdout.write(f"  -> patched mcp server description: {updated_server.description!r}")

        # ── 4. persona.delete / mcp_server.delete ────────────────────────────
        self._section("4. DELETE -- persona.delete (obj=project) / mcp_server.delete (obj=server)")
        self._check("owner can persona.delete", PermissionChecker.can(owner, "persona.delete", obj=project), True)
        self._check("project_admin can persona.delete (own project's persona)", PermissionChecker.can(project_admin, "persona.delete", obj=project), True)
        self._check("owner can mcp_server.delete", PermissionChecker.can(owner, "mcp_server.delete", obj=server), True)
        self._check("project_admin can mcp_server.delete (own project's server)", PermissionChecker.can(project_admin, "mcp_server.delete", obj=server), True)
        self._check("other_admin can mcp_server.delete (different project)", PermissionChecker.can(other_admin, "mcp_server.delete", obj=server), False)

        # Persona first: delete_mcp_server_standalone refuses while any active
        # persona still mounts the server.
        result = isvc.delete_persona(company, str(persona.id))
        self.stdout.write(f"  -> delete_persona returned: {result}")
        server_result = isvc.delete_mcp_server_standalone(company, str(server.id))
        self.stdout.write(f"  -> delete_mcp_server_standalone returned: {server_result}")

        persona.refresh_from_db()
        server.refresh_from_db()
        self.stdout.write(f"  -> persona.is_active after delete: {persona.is_active}")
        self.stdout.write(f"  -> server.is_active after delete: {server.is_active}")

        owner_sees_after = [p.name for p in isvc.list_personas(project, owner)]
        self.stdout.write(f"  -> owner's list_personas after delete (expect gone): {owner_sees_after}")

        self._line()
        self.stdout.write(self.style.SUCCESS("Done."))

    # ── helpers ──────────────────────────────────────────────────────────────

    def _line(self):
        self.stdout.write("=" * 78)

    def _section(self, title):
        self.stdout.write("")
        self.stdout.write(self.style.NOTICE(f"-- {title} --"))

    def _check(self, label, actual, expected):
        match = actual == expected
        marker = "PASS" if match else "FAIL"
        style = self.style.SUCCESS if match else self.style.ERROR
        self.stdout.write(style(f"  [{marker}] {label}: {actual} (expected {expected})"))
