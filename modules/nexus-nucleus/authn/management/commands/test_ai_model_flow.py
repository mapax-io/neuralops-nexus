"""
Management command: python manage.py test_ai_model_flow

Exercises the full ModelConfig lifecycle -- create -> list -> attach ->
detach -> delete -- plus the RBAC rights checks around each step. Same shape
as test_persona_flow.py / test_agent_flow.py / test_mcp_server_flow.py.

AIModel was renamed to ModelConfig and every ai_model.* right code became
model_config.*, so both halves of this command were repointed. The scope
rules themselves are unchanged.

Rights being verified (see authn/permissions/rights.py + USE_CASES.md UC14/UC15):
    model_config.create / model_config.delete are COMPANY scope ONLY --
    unlike MCPServer/Persona, a Project Admin never reaches these
    regardless of which project they administer, because creating/deleting
    a config touches the Fernet-encrypted API key. This command's
    project_admin (Project Admin on `project`, no company-wide role) should
    be denied on both create and delete.

    model_config.attach is the deliberate exception -- PROJECT scope,
    checked as obj=project, never touches the key. project_admin SHOULD
    reach this on their own project (and detach, which reuses the same
    right code), but not on a different project (other_admin).

    Also demonstrates the "unattached = invisible to everyone but a
    company-wide list holder" rule from UC13/UC15: right after creation,
    before any attach call, project_admin's list_model_configs() comes back
    empty even though they're a genuine member of `project` -- attachment
    is what makes a config visible via the narrow/row-visibility path, not
    just being in a project at all.
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from authn.permissions.checker import PermissionChecker
from authn.permissions.models import Role
from intelligence import services as isvc
from nucleus.models import Company, ModelConfig, Project

User = get_user_model()

_MODEL_NAME = "Test Model for Model Config Flow"


class Command(BaseCommand):
    help = "Exercise the full ModelConfig CRUD + attach/detach lifecycle + rights checks in one run."

    def handle(self, *args, **options):
        self._line()
        self.stdout.write(self.style.NOTICE("Model Config lifecycle test (create -> list -> attach -> detach -> delete)"))
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
            company=company, slug="other-project-ai-model-flow",
            defaults={"name": "Other Project (ai model flow isolation test)"},
        )

        self.stdout.write(f"Company: {company.name} | Owner: {owner.email} | "
                           f"Project: {project.name} | Other project: {other_project.name}")

        admin_role = Role.objects.filter(company=company, name="Admin").first()

        project_admin, created = User.objects.get_or_create(
            username="test_project_admin_ai_model_flow",
            defaults={"email": "test_project_admin_ai_model_flow@test.local", "user_type": "human"},
        )
        if admin_role:
            PermissionChecker.assign_role(project_admin, admin_role, project, granted_by=owner)
        self.stdout.write(f"Test user 1: {project_admin.username} (Project Admin on '{project.name}' only) "
                           f"{'[created]' if created else '[reused]'}")

        other_admin, created2 = User.objects.get_or_create(
            username="test_other_project_admin_ai_model_flow",
            defaults={"email": "test_other_project_admin_ai_model_flow@test.local", "user_type": "human"},
        )
        if admin_role:
            PermissionChecker.assign_role(other_admin, admin_role, other_project, granted_by=owner)
        self.stdout.write(f"Test user 2: {other_admin.username} (Project Admin on '{other_project.name}' only) "
                           f"{'[created]' if created2 else '[reused]'}")

        # ── 1. model_config.create -- COMPANY scope ONLY ────────────────────
        self._section("1. CREATE -- model_config.create (COMPANY scope ONLY -- touches the API key)")
        self._check("owner can model_config.create", PermissionChecker.can(owner, "model_config.create", company=company), True)
        self._check("project_admin can model_config.create -- EXPECT False, no project-scope path for this right",
                     PermissionChecker.can(project_admin, "model_config.create", company=company), False)

        # provider and the BARE model name are two columns now -- passing
        # "openai/gpt-flow-test" as model_id is rejected outright by
        # create_model_config's prefix guard. qualified_id composes the
        # "provider:model" wire string.
        #
        # Reused rather than recreated when a previous run left it behind:
        # uniq_model_config_name_per_company does not ignore soft-deleted
        # rows, so a second create with the same name would be an
        # IntegrityError.
        model = ModelConfig.objects.filter(company=company, name=_MODEL_NAME).first()
        if model is None:
            model = isvc.create_model_config(company, owner, {
                "name": _MODEL_NAME, "provider": "openai", "model_id": "gpt-flow-test",
                "api_key": "sk-fake-flow-test-key", "licence_accepted": True,
            })
        elif not model.is_active:
            model.restore()
        self.stdout.write(f"  -> model config created: id={model.id} name={model.name!r} "
                           f"qualified_id={model.qualified_id!r} has_api_key={bool(model.api_key_encrypted)}")

        # ── 2. model_config.list + visibility BEFORE attach ─────────────────
        self._section("2. LIST (before attach) -- unattached configs are invisible to everyone but a company-wide holder")
        self._check("owner can model_config.list (company-wide)", PermissionChecker.can(owner, "model_config.list", company=company), True)
        self._check("project_admin can model_config.list (company-wide)", PermissionChecker.can(project_admin, "model_config.list", company=company), False)

        owner_sees = [m.name for m in isvc.list_model_configs(company, owner)]
        admin_sees_before = [m.name for m in isvc.list_model_configs(company, project_admin)]
        self.stdout.write(f"  -> owner's list_model_configs: {owner_sees}")
        self.stdout.write(f"  -> project_admin's list_model_configs BEFORE attach "
                           f"(expect [] -- unattached, even though they're a real member of '{project.name}'): {admin_sees_before}")

        # ── 3. model_config.attach -- PROJECT scope, the deliberate exception ──
        self._section("3. ATTACH -- model_config.attach (PROJECT scope, obj=project, never touches the key)")
        self._check("owner can model_config.attach to project", PermissionChecker.can(owner, "model_config.attach", obj=project), True)
        self._check("project_admin can model_config.attach to project (own project)", PermissionChecker.can(project_admin, "model_config.attach", obj=project), True)
        self._check("other_admin can model_config.attach to project (different project)", PermissionChecker.can(other_admin, "model_config.attach", obj=project), False)

        attach_result = isvc.attach_model_config_to_project(company, str(model.id), str(project.id))
        self.stdout.write(f"  -> attach_model_config_to_project returned: {attach_result}")

        admin_sees_after = [m.name for m in isvc.list_model_configs(company, project_admin)]
        self.stdout.write(f"  -> project_admin's list_model_configs AFTER attach (expect to see it now): {admin_sees_after}")

        # ── 4. model_config.attach (detach uses the SAME right code) ───────
        self._section("4. DETACH -- same 'model_config.attach' right code as step 3, checked identically")
        self._check("owner can detach (model_config.attach)", PermissionChecker.can(owner, "model_config.attach", obj=project), True)
        self._check("project_admin can detach (own project)", PermissionChecker.can(project_admin, "model_config.attach", obj=project), True)
        self._check("other_admin can detach (different project)", PermissionChecker.can(other_admin, "model_config.attach", obj=project), False)

        # Raises ValueError if a persona in this project still uses the
        # config, as either its primary or its advisor -- nothing does here,
        # since this command creates its own throwaway config.
        detach_result = isvc.detach_model_config_from_project(company, str(model.id), str(project.id))
        self.stdout.write(f"  -> detach_model_config_from_project returned: {detach_result}")

        admin_sees_after_detach = [m.name for m in isvc.list_model_configs(company, project_admin)]
        self.stdout.write(f"  -> project_admin's list_model_configs AFTER detach (expect [] again): {admin_sees_after_detach}")

        # ── 4b. model_config.update -- COMPANY scope; provider/model_id now patchable ──
        self._section("4b. PATCH -- provider/model_id repoint every persona on the config; guards match create")
        self._check("owner can model_config.update", PermissionChecker.can(owner, "model_config.update", company=company), True)
        self._check("project_admin can model_config.update -- EXPECT False (COMPANY scope)",
                    PermissionChecker.can(project_admin, "model_config.update", company=company), False)
        before = model.qualified_id
        patched = isvc.update_model_config(company, str(model.id), {"provider": "anthropic", "model_id": "claude-test-flow"})
        self._check("qualified_id follows the patched provider + bare id",
                    patched.qualified_id, "anthropic:claude-test-flow")
        self.stdout.write(f"  -> qualified_id {before!r} -> {patched.qualified_id!r}")
        for bad, label in (({"model_id": "openai/gpt-4o"}, "prefixed model_id refused"),
                           ({"provider": "litellm"}, "unknown provider refused")):
            try:
                isvc.update_model_config(company, str(model.id), dict(bad))
                self._check(label, "accepted", "ValueError")
            except ValueError as exc:
                self._check(label, "ValueError", "ValueError")
                self.stdout.write(f"     ({exc})")
        # Restore the throwaway config's identity for the delete step / reruns.
        isvc.update_model_config(company, str(model.id), {"provider": model.provider, "model_id": model.model_id})

        # ── 5. model_config.delete -- COMPANY scope ONLY ────────────────────
        self._section("5. DELETE -- model_config.delete (COMPANY scope ONLY)")
        self._check("owner can model_config.delete", PermissionChecker.can(owner, "model_config.delete", company=company), True)
        self._check("project_admin can model_config.delete -- EXPECT False", PermissionChecker.can(project_admin, "model_config.delete", company=company), False)

        delete_result = isvc.delete_model_config(company, str(model.id))
        self.stdout.write(f"  -> delete_model_config returned: {delete_result}")
        model.refresh_from_db()
        self.stdout.write(f"  -> model.is_active after delete: {model.is_active}")

        owner_sees_after = [m.name for m in isvc.list_model_configs(company, owner)]
        self.stdout.write(f"  -> owner's list_model_configs after delete (expect gone): {owner_sees_after}")

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
