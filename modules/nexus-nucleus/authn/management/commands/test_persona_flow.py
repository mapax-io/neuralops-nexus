"""
Management command: python manage.py test_persona_flow

Exercises the full Persona lifecycle -- create -> list -> patch -> delete --
plus the RBAC rights checks around each step, in one run. No shell
copy-paste required; read the printed output top to bottom.

Rights being verified throughout (see authn/permissions/rights.py):
    persona.create / persona.update / persona.delete are PROJECT scope -- a
    persona belongs to exactly one project, and that project's own Admin
    manages it without company-wide access, the same shape mcp_server.*
    has. persona.list stays COMPANY scope for the blanket check. So this
    command creates a second user who is Project Admin on the test project
    but holds NO company-wide role: every persona write check comes back
    True for them, persona.list comes back False, and list_personas()
    (row-visibility, not a blanket check) still lets them see it -- same
    "list never just 403s" pattern as every other resource type.
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from authn.permissions.checker import PermissionChecker
from authn.permissions.models import Role
from intelligence import services as isvc
from nucleus.models import Company, ModelConfig, Project

User = get_user_model()

_MODEL_NAME = "Test Model for Persona Flow"


class Command(BaseCommand):
    help = "Exercise the full Persona CRUD lifecycle + rights checks in one run."

    def handle(self, *args, **options):
        self._line()
        self.stdout.write(self.style.NOTICE("Persona lifecycle test (create -> list -> patch -> delete)"))
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

        # A throwaway ModelConfig, reused across runs: model_id is the BARE
        # name (provider is its own column now) and
        # uniq_model_config_name_per_company does not ignore soft-deleted
        # rows, so recreating it blindly would be an IntegrityError.
        model = ModelConfig.objects.filter(company=company, name=_MODEL_NAME).first()
        if not model:
            self.stdout.write("No throwaway ModelConfig found -- creating one for this test.")
            model = isvc.create_model_config(company, owner, {
                "name": _MODEL_NAME, "provider": "openai", "model_id": "gpt-test",
                "licence_accepted": True,
            })
        elif not model.is_active:
            model.restore()

        # A persona may only use a config attached to its own project --
        # _validate_persona_wiring refuses an unattached one.
        isvc.attach_model_config_to_project(company, str(model.id), str(project.id))

        self.stdout.write(f"Company: {company.name} | Owner: {owner.email} | "
                           f"Project: {project.name} | Model: {model.name}")

        # A second user: Project Admin on `project` ONLY, no company-wide role at
        # all. This is the user every persona.* can() check below must deny.
        project_admin, created = User.objects.get_or_create(
            username="test_project_admin_persona_flow",
            defaults={"email": "test_project_admin_persona_flow@test.local", "user_type": "human"},
        )
        admin_role = Role.objects.filter(company=company, name="Admin").first()
        if admin_role:
            PermissionChecker.assign_role(project_admin, admin_role, project, granted_by=owner)
        self.stdout.write(f"Test user: {project_admin.username} (Project Admin on '{project.name}' only, "
                           f"no company-wide role) {'[created]' if created else '[reused]'}")

        # ── 1. persona.create ────────────────────────────────────────────────
        self._section("1. CREATE -- persona.create (PROJECT scope)")
        self._check("owner can create_persona", PermissionChecker.can(owner, "persona.create", obj=project), True)
        self._check("project_admin can create_persona", PermissionChecker.can(project_admin, "persona.create", obj=project), True)

        persona = isvc.create_persona(company, owner, {
            "name": "Nova Test Flow",
            "description": "Created by test_persona_flow management command.",
            "project_id": str(project.id),
            "model_config_id": str(model.id),
            "prompt": {
                "system_prompt": "You are Nova, a test persona.",
                "output_type": "text",
                "context_scope": "topic",
            },
        })
        self.stdout.write(f"  -> persona created: id={persona.id} name={persona.name!r} "
                           f"is_active={persona.is_active}")

        # ── 2. persona.list / visible_personas ──────────────────────────────
        self._section("2. LIST -- persona.list (blanket) vs visible_personas (row-visibility)")
        self._check("owner can persona.list (company-wide)", PermissionChecker.can(owner, "persona.list", company=company), True)
        self._check("project_admin can persona.list (company-wide)", PermissionChecker.can(project_admin, "persona.list", company=company), False)

        owner_sees = [p.name for p in isvc.list_personas(project, owner)]
        admin_sees = [p.name for p in isvc.list_personas(project, project_admin)]
        self.stdout.write(f"  -> owner's list_personas(project): {owner_sees}")
        self.stdout.write(f"  -> project_admin's list_personas(project) (expect to still see it -- "
                           f"narrow-path reach via their own project membership): {admin_sees}")

        # ── 3. persona.update ────────────────────────────────────────────────
        self._section("3. PATCH -- persona.update (PROJECT scope)")
        self._check("owner can persona.update", PermissionChecker.can(owner, "persona.update", obj=project), True)
        self._check("project_admin can persona.update", PermissionChecker.can(project_admin, "persona.update", obj=project), True)

        updated = isvc.patch_persona(company, str(persona.id), {"description": "Updated by test_persona_flow."})
        self.stdout.write(f"  -> patched description: {updated.description!r}")

        # ── 4. persona.delete ────────────────────────────────────────────────
        self._section("4. DELETE -- persona.delete (PROJECT scope)")
        self._check("owner can persona.delete", PermissionChecker.can(owner, "persona.delete", obj=project), True)
        self._check("project_admin can persona.delete", PermissionChecker.can(project_admin, "persona.delete", obj=project), True)

        result = isvc.delete_persona(company, str(persona.id))
        self.stdout.write(f"  -> delete_persona returned: {result}")

        persona.refresh_from_db()
        self.stdout.write(f"  -> persona.is_active after delete: {persona.is_active}")
        self.stdout.write(f"  -> persona.name after delete (mangled by design -- see delete_persona): {persona.name!r}")

        owner_sees_after = [p.name for p in isvc.list_personas(project, owner)]
        self.stdout.write(f"  -> list_personas(project) after delete (expect gone): {owner_sees_after}")

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
