"""
Management command: python manage.py test_mcp_server_flow

Exercises the MCP server lifecycle -- create -> list -> patch -> delete --
plus the RBAC rights checks around each step. Same shape as
test_persona_flow.py / test_agent_flow.py.

Rights being verified (see authn/permissions/rights.py + intelligence/api.py):
    mcp_server.create/update/delete are PROJECT scope, checked as
    obj=project (create) or obj=server (update/delete). A Project Admin on
    the server's own project reaches these with no company-wide role --
    the pattern agent.* used to share before AIAgent was removed.

    Part 2 keeps the other half of the old story: the SAME right codes
    anchored at company=company instead of obj=project/obj=server. A
    PROJECT-scope RoleAssignment never matches a chain rooted only at
    COMPANY, so the same Project Admin who passes every check in Part 1
    gets denied on all three here. That used to be demonstrated through
    the legacy nested endpoints (ai-models/{model_id}/mcp-servers/); those
    endpoints and their model-scoped service functions
    (create_mcp_server / list_mcp_servers / delete_mcp_server) are gone
    with AIAgent -- they reached servers via `agents__model__id` -- so the
    checks are shown against the standalone calls instead.
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from authn.permissions.checker import PermissionChecker
from authn.permissions.models import Role
from intelligence import services as isvc
from nucleus.models import Company, MCPServer, Project

User = get_user_model()


class Command(BaseCommand):
    help = "Exercise the full MCPServer CRUD lifecycle (standalone + legacy) + rights checks in one run."

    def handle(self, *args, **options):
        self._line()
        self.stdout.write(self.style.NOTICE("MCP Server lifecycle test (standalone + legacy nested)"))
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
            company=company, slug="other-project-mcp-flow",
            defaults={"name": "Other Project (mcp flow isolation test)"},
        )

        # No throwaway AIModel any more -- MCP servers are project-owned
        # through a real `project` FK and never hung off a model.

        # Hard-delete leftovers from a previous run:
        # uniq_mcp_server_name_per_project does not ignore soft-deleted rows,
        # so a name freed only by this command's own delete step would still
        # collide on the next create.
        MCPServer.objects.filter(
            project=project,
            name__in=["Search MCP Test Flow", "Search MCP Test Flow v2", "Company Anchored MCP Test Flow"],
        ).delete()

        self.stdout.write(f"Company: {company.name} | Owner: {owner.email} | "
                           f"Project: {project.name} | Other project: {other_project.name}")

        admin_role = Role.objects.filter(company=company, name="Admin").first()

        project_admin, created = User.objects.get_or_create(
            username="test_project_admin_mcp_flow",
            defaults={"email": "test_project_admin_mcp_flow@test.local", "user_type": "human"},
        )
        if admin_role:
            PermissionChecker.assign_role(project_admin, admin_role, project, granted_by=owner)
        self.stdout.write(f"Test user 1: {project_admin.username} (Project Admin on '{project.name}' only) "
                           f"{'[created]' if created else '[reused]'}")

        other_admin, created2 = User.objects.get_or_create(
            username="test_other_project_admin_mcp_flow",
            defaults={"email": "test_other_project_admin_mcp_flow@test.local", "user_type": "human"},
        )
        if admin_role:
            PermissionChecker.assign_role(other_admin, admin_role, other_project, granted_by=owner)
        self.stdout.write(f"Test user 2: {other_admin.username} (Project Admin on '{other_project.name}' only) "
                           f"{'[created]' if created2 else '[reused]'}")

        # ══════════════════════════════════════════════════════════════════════
        # PART 1 — Flat / standalone endpoints (mcp-servers/)
        # ══════════════════════════════════════════════════════════════════════

        self._section("PART 1 — Standalone: CREATE -- mcp_server.create (PROJECT scope, obj=project)")
        self._check("owner can mcp_server.create on project", PermissionChecker.can(owner, "mcp_server.create", obj=project), True)
        self._check("project_admin can mcp_server.create on project (own project)", PermissionChecker.can(project_admin, "mcp_server.create", obj=project), True)
        self._check("other_admin can mcp_server.create on project (different project)", PermissionChecker.can(other_admin, "mcp_server.create", obj=project), False)

        server = isvc.create_mcp_server_standalone(company, {
            "name": "Search MCP Test Flow",
            "project_id": str(project.id),
            "server_type": "remote",
            "transport": "http",
            "url": "https://example.test/mcp-flow",
        })
        self.stdout.write(f"  -> server created: id={server.id} name={server.name!r} is_active={server.is_active}")

        self._section("PART 1 — Standalone: LIST -- mcp_server.list (blanket) vs visible_mcp_servers (row-visibility)")
        self._check("owner can mcp_server.list (company-wide)", PermissionChecker.can(owner, "mcp_server.list", company=company), True)
        self._check("project_admin can mcp_server.list (company-wide)", PermissionChecker.can(project_admin, "mcp_server.list", company=company), False)

        owner_sees = [s.name for s in isvc.list_mcp_servers_all(company, owner)]
        admin_sees = [s.name for s in isvc.list_mcp_servers_all(company, project_admin)]
        other_admin_sees = [s.name for s in isvc.list_mcp_servers_all(company, other_admin)]
        self.stdout.write(f"  -> owner's list_mcp_servers_all: {owner_sees}")
        self.stdout.write(f"  -> project_admin's list_mcp_servers_all (expect to still see it): {admin_sees}")
        self.stdout.write(f"  -> other_admin's list_mcp_servers_all (expect NOT to see it): {other_admin_sees}")

        self._section("PART 1 — Standalone: PATCH -- mcp_server.update (PROJECT scope, obj=server)")
        self._check("owner can mcp_server.update", PermissionChecker.can(owner, "mcp_server.update", obj=server), True)
        self._check("project_admin can mcp_server.update (own project's server)", PermissionChecker.can(project_admin, "mcp_server.update", obj=server), True)
        self._check("other_admin can mcp_server.update (different project)", PermissionChecker.can(other_admin, "mcp_server.update", obj=server), False)

        updated = isvc.update_mcp_server_standalone(company, str(server.id), {"name": "Search MCP Test Flow v2"})
        self.stdout.write(f"  -> patched name: {updated.name!r}")

        self._section("PART 1 — Standalone: DELETE -- mcp_server.delete (PROJECT scope, obj=server)")
        self._check("owner can mcp_server.delete", PermissionChecker.can(owner, "mcp_server.delete", obj=server), True)
        self._check("project_admin can mcp_server.delete (own project's server)", PermissionChecker.can(project_admin, "mcp_server.delete", obj=server), True)
        self._check("other_admin can mcp_server.delete (different project)", PermissionChecker.can(other_admin, "mcp_server.delete", obj=server), False)

        result = isvc.delete_mcp_server_standalone(company, str(server.id))
        self.stdout.write(f"  -> delete_mcp_server_standalone returned: {result}")
        server.refresh_from_db()
        self.stdout.write(f"  -> server.is_active after delete: {server.is_active}")

        # ══════════════════════════════════════════════════════════════════════
        # PART 2 — The same right codes, anchored at company=company
        # ══════════════════════════════════════════════════════════════════════

        self._section("PART 2 — CREATE -- mcp_server.create checked as company=company (NOT obj=project)")
        self._check("owner can mcp_server.create (company-wide)", PermissionChecker.can(owner, "mcp_server.create", company=company), True)
        self._check("project_admin can mcp_server.create (company-wide) -- EXPECT False here even though it was True in Part 1",
                     PermissionChecker.can(project_admin, "mcp_server.create", company=company), False)

        # The model-scoped create_mcp_server(company, model_id, data) is gone
        # -- it reached servers through `agents__model__id` and raised
        # TypeError on every call anyway. project_id rides in the payload now.
        second_server = isvc.create_mcp_server_standalone(company, {
            "name": "Company Anchored MCP Test Flow", "project_id": str(project.id),
            "server_type": "remote", "transport": "http",
            "url": "https://example.test/company-anchored-flow",
        })
        self.stdout.write(f"  -> server created: id={second_server.id} name={second_server.name!r} "
                           f"project={second_server.project.name}")

        self._section("PART 2 — LIST -- mcp_server.list checked as company=company")
        self._check("owner can mcp_server.list (company-wide)", PermissionChecker.can(owner, "mcp_server.list", company=company), True)
        # list_mcp_servers(company, model_id) is gone -- there is no model to
        # scope a server list to any more, only the row-visibility rule.
        owner_list = [s.name for s in isvc.list_mcp_servers_all(company, owner)]
        self.stdout.write(f"  -> list_mcp_servers_all(owner): {owner_list}")

        self._section("PART 2 — DELETE -- mcp_server.delete checked as company=company")
        self._check("owner can mcp_server.delete (company-wide)", PermissionChecker.can(owner, "mcp_server.delete", company=company), True)
        self._check("project_admin can mcp_server.delete (company-wide) -- EXPECT False, same asymmetry as create",
                     PermissionChecker.can(project_admin, "mcp_server.delete", company=company), False)

        second_result = isvc.delete_mcp_server_standalone(company, str(second_server.id))
        self.stdout.write(f"  -> delete_mcp_server_standalone returned: {second_result}")
        second_server.refresh_from_db()
        self.stdout.write(f"  -> second_server.is_active after delete: {second_server.is_active}")

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
