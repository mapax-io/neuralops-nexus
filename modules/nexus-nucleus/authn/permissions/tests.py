"""
authn/permissions/tests.py

Test cases for the permission system, one per use case in USE_CASES.md
(read that first — these tests exist to prove those scenarios actually
behave the way they're described, not to replace it).

Run with:
    python manage.py test authn.permissions

Uses Django's built-in TestCase (matches the rest of this codebase —
see authn/tests.py — no pytest dependency here).
"""
from django.contrib.auth import get_user_model
from django.test import TestCase

from nucleus.models import Company, Project, Channel, ChatTopic, ModelConfig, MCPServer, Persona

from .checker import PermissionChecker
from .models import Right, Role, RoleAssignment, RoleRight
from .rights import DEFAULT_ROLE_RIGHTS, REGISTRY
from .row_rules import visible_model_configs, visible_mcp_servers, visible_personas

User = get_user_model()


class RegistryConsistencyTests(TestCase):
    """
    Sanity checks on the plain-Python data in rights.py, with no database
    involved. These would have caught the typo-guard warning that
    seed_permissions prints at runtime, before ever running the command.
    """

    def test_every_default_role_right_exists_in_registry(self):
        known_codes = {code for code, *_ in REGISTRY}
        for role_name, right_codes in DEFAULT_ROLE_RIGHTS.items():
            for code in right_codes:
                self.assertIn(
                    code, known_codes,
                    f"DEFAULT_ROLE_RIGHTS['{role_name}'] references '{code}', "
                    f"which is not in REGISTRY.",
                )

    def test_registry_codes_are_unique(self):
        codes = [code for code, *_ in REGISTRY]
        self.assertEqual(len(codes), len(set(codes)), "Duplicate right code in REGISTRY.")

    def test_company_wide_ai_rights_excluded_from_member_and_viewer(self):
        """
        Locks in the decision from the design discussion: persona/
        mcp_server/model_config create+delete rights must never be handed
        to Member or Viewer by default, regardless of scope.

        The agent.* codes this used to also guard are gone -- AIAgent was
        removed and Persona absorbed it, so there is nothing left to check.
        """
        forbidden_prefixes = ("persona.create", "persona.update", "persona.delete",
                               "mcp_server.create", "mcp_server.delete",
                               "model_config.create", "model_config.delete")
        for role_name in ("Member", "Viewer"):
            granted = set(DEFAULT_ROLE_RIGHTS[role_name])
            overlap = granted.intersection(forbidden_prefixes)
            self.assertFalse(
                overlap,
                f"{role_name} must not hold company-wide infra rights, found: {overlap}",
            )


class PermissionCheckerTestCase(TestCase):
    """
    Base fixture shared by the behavioural tests below: one company, one
    project, one channel, two topics, three users, and just the Right /
    Role / RoleRight rows the tests actually need (not the full registry
    — keeps each test's intent readable without a database round trip
    through the management command).
    """

    def setUp(self):
        self.company = Company.objects.create(name="Acme", slug="acme")

        self.owner = User.objects.create_user(username="noaman", email="noaman@acme.test", password="x")
        self.company.owner = self.owner
        self.company.save(update_fields=["owner"])

        self.sara = User.objects.create_user(username="sara", email="sara@acme.test", password="x")
        self.ali = User.objects.create_user(username="ali", email="ali@acme.test", password="x")

        self.project = Project.objects.create(company=self.company, name="Q3 Launch", slug="q3-launch")
        self.channel = Channel.objects.create(
            company=self.company, project=self.project, name="general", slug="general",
        )
        self.topic_a = ChatTopic.objects.create(
            company=self.company, project=self.project, channel=self.channel,
            title="Topic A", slug="topic-a",
        )
        self.topic_b = ChatTopic.objects.create(
            company=self.company, project=self.project, channel=self.channel,
            title="Topic B", slug="topic-b",
        )

        # Only the rights these tests exercise -- not the full REGISTRY.
        self.r_project_create = Right.objects.create(code="project.create", object_type="project", scope="company")
        self.r_channel_create = Right.objects.create(code="channel.create", object_type="channel", scope="project")
        self.r_topic_mark_read = Right.objects.create(code="topic.mark_read", object_type="topic", scope="topic")
        self.r_persona_create = Right.objects.create(code="persona.create", object_type="persona", scope="company")
        self.r_persona_mention = Right.objects.create(code="persona.mention", object_type="persona", scope="topic")

        self.role_company_admin = Role.objects.create(
            company=self.company, name="Admin", scope="company", description="Company-wide admin.",
        )
        for right in (self.r_project_create, self.r_channel_create, self.r_topic_mark_read,
                      self.r_persona_create, self.r_persona_mention):
            RoleRight.objects.create(role=self.role_company_admin, right=right)

        self.role_project_admin = Role.objects.create(
            company=self.company, name="Admin", scope="project", description="Project-scoped admin.",
        )
        for right in (self.r_channel_create, self.r_topic_mark_read, self.r_persona_mention):
            RoleRight.objects.create(role=self.role_project_admin, right=right)
        # Deliberately NOT granted persona.create at project scope -- see UC6.

        self.role_topic_member = Role.objects.create(
            company=self.company, name="Member", scope="topic", description="Topic-scoped member.",
        )
        RoleRight.objects.create(role=self.role_topic_member, right=self.r_topic_mark_read)
        RoleRight.objects.create(role=self.role_topic_member, right=self.r_persona_mention)


class UC1_CreateProjectTests(PermissionCheckerTestCase):
    """UC1 -- creating a project is a Company-scope right, checked before any Project exists."""

    def test_company_admin_can_create_project(self):
        PermissionChecker.assign_role(self.sara, self.role_company_admin, self.company)
        self.assertTrue(
            PermissionChecker.can(self.sara, "project.create", company=self.company)
        )

    def test_user_with_no_assignment_cannot_create_project(self):
        self.assertFalse(
            PermissionChecker.can(self.ali, "project.create", company=self.company)
        )


class UC3_ProjectAdminCreatesChannelTests(PermissionCheckerTestCase):
    """UC3 -- a Project-scoped assignment reaches down to grant channel.create on that project."""

    def test_project_scoped_admin_can_create_channel_on_own_project(self):
        PermissionChecker.assign_role(self.sara, self.role_project_admin, self.project)
        self.assertTrue(
            PermissionChecker.can(self.sara, "channel.create", obj=self.project)
        )

    def test_project_scoped_admin_cannot_act_on_a_different_project(self):
        other_project = Project.objects.create(company=self.company, name="Other", slug="other")
        PermissionChecker.assign_role(self.sara, self.role_project_admin, self.project)
        self.assertFalse(
            PermissionChecker.can(self.sara, "channel.create", obj=other_project)
        )


class UC4_TopicScopedMemberVisibilityTests(PermissionCheckerTestCase):
    """UC4 -- a Topic-scoped assignment reaches only that topic, not sibling topics."""

    def test_topic_member_has_rights_on_own_topic(self):
        PermissionChecker.assign_role(self.ali, self.role_topic_member, self.topic_a)
        self.assertTrue(
            PermissionChecker.can(self.ali, "topic.mark_read", obj=self.topic_a)
        )

    def test_topic_member_has_no_rights_on_sibling_topic(self):
        PermissionChecker.assign_role(self.ali, self.role_topic_member, self.topic_a)
        self.assertFalse(
            PermissionChecker.can(self.ali, "topic.mark_read", obj=self.topic_b)
        )


class UC5_PromotionIsAdditiveTests(PermissionCheckerTestCase):
    """UC5 -- promoting to a broader scope doesn't remove the narrower assignment, and both apply."""

    def test_promoting_to_project_admin_grants_full_project_reach(self):
        PermissionChecker.assign_role(self.ali, self.role_topic_member, self.topic_a)
        PermissionChecker.assign_role(self.ali, self.role_project_admin, self.project)

        # Now reaches topic_b too, even though the original assignment was only on topic_a.
        self.assertTrue(
            PermissionChecker.can(self.ali, "topic.mark_read", obj=self.topic_b)
        )
        # The original narrower assignment still exists and still works.
        self.assertTrue(
            PermissionChecker.can(self.ali, "topic.mark_read", obj=self.topic_a)
        )
        self.assertEqual(RoleAssignment.objects.filter(user=self.ali).count(), 2)


class UC6_UC7_CompanyWideRightsScopeTests(PermissionCheckerTestCase):
    """UC6/UC7 -- persona.create is COMPANY scope only; a Project-scoped Admin must not inherit it."""

    def test_project_scoped_admin_cannot_create_persona(self):
        PermissionChecker.assign_role(self.ali, self.role_project_admin, self.project)
        self.assertFalse(
            PermissionChecker.can(self.ali, "persona.create", company=self.company)
        )

    def test_company_scoped_admin_can_create_persona(self):
        PermissionChecker.assign_role(self.sara, self.role_company_admin, self.company)
        self.assertTrue(
            PermissionChecker.can(self.sara, "persona.create", company=self.company)
        )


class UC8_StackedCapabilityRoleTests(PermissionCheckerTestCase):
    """UC8 -- a small additive role grants exactly one extra right, without a full promotion."""

    def test_stacked_capability_role_grants_only_its_own_rights(self):
        builder_role = Role.objects.create(
            company=self.company, name="Persona Builder", scope="company",
            description="Can create personas only.",
        )
        RoleRight.objects.create(role=builder_role, right=self.r_persona_create)

        PermissionChecker.assign_role(self.ali, self.role_project_admin, self.project)  # base tier
        PermissionChecker.assign_role(self.ali, builder_role, self.company)  # stacked capability

        self.assertTrue(
            PermissionChecker.can(self.ali, "persona.create", company=self.company),
            "Stacked capability role should grant persona.create.",
        )
        self.assertFalse(
            PermissionChecker.can(self.ali, "project.create", company=self.company),
            "Builder role must not also grant unrelated rights like project.create.",
        )


class UC10_ViewerCannotMentionTests(PermissionCheckerTestCase):
    """UC10 -- a role that never grants persona.mention correctly denies AI triggering."""

    def test_role_without_mention_right_is_denied(self):
        read_only_role = Role.objects.create(
            company=self.company, name="Viewer", scope="topic", description="Read-only.",
        )
        RoleRight.objects.create(role=read_only_role, right=self.r_topic_mark_read)
        # Deliberately no persona.mention grant.

        PermissionChecker.assign_role(self.ali, read_only_role, self.topic_a)

        self.assertTrue(PermissionChecker.can(self.ali, "topic.mark_read", obj=self.topic_a))
        self.assertFalse(PermissionChecker.can(self.ali, "persona.mention", obj=self.topic_a))


class UC12_RightsForTests(PermissionCheckerTestCase):
    """UC12 -- rights_for() returns the full union in one call, for a frontend permissions payload."""

    def test_rights_for_returns_union_of_all_applicable_roles(self):
        PermissionChecker.assign_role(self.ali, self.role_topic_member, self.topic_a)
        rights = PermissionChecker.rights_for(self.ali, obj=self.topic_a)
        self.assertEqual(rights, {"topic.mark_read", "persona.mention"})

    def test_rights_for_returns_empty_set_with_no_assignment(self):
        rights = PermissionChecker.rights_for(self.ali, obj=self.topic_a)
        self.assertEqual(rights, set())

    def test_rights_for_narrows_by_right_scope_like_can_does(self):
        """
        A company-scoped right must NOT be reported for a topic-scoped
        assignment. rights_for() used to return every right on every matching
        role, so it claimed rights can() denies -- and that payload is what
        the frontend draws its buttons from.
        """
        # Give the topic-scoped role a company-scoped right it can never reach.
        RoleRight.objects.create(role=self.role_topic_member, right=self.r_persona_create)
        PermissionChecker.assign_role(self.ali, self.role_topic_member, self.topic_a)

        rights = PermissionChecker.rights_for(self.ali, obj=self.topic_a)
        self.assertNotIn("persona.create", rights)
        self.assertEqual(rights, {"topic.mark_read", "persona.mention"})
        # ... and it now agrees with can(), which is the point.
        self.assertFalse(PermissionChecker.can(self.ali, "persona.create", obj=self.topic_a))

    def test_rights_for_keeps_levels_separate_when_roles_differ(self):
        """
        Viewer at company + Admin on one project: the project row must not
        hand out company-scoped rights, and the company row must still grant
        the ones it legitimately holds.
        """
        viewer = Role.objects.create(
            company=self.company, name="Viewer", scope="company", description="Read-only.",
        )
        RoleRight.objects.create(role=viewer, right=self.r_topic_mark_read)

        PermissionChecker.assign_role(self.ali, viewer, self.company)
        PermissionChecker.assign_role(self.ali, self.role_project_admin, self.project)

        rights = PermissionChecker.rights_for(self.ali, obj=self.project)
        # From the project-scoped Admin row (project/topic-scoped rights).
        self.assertIn("channel.create", rights)
        # persona.create is COMPANY-scoped and only the Viewer row is anchored
        # there -- the Admin row must not reach up to grant it.
        self.assertNotIn("persona.create", rights)
        self.assertFalse(PermissionChecker.can(self.ali, "persona.create", obj=self.project))

    def test_rights_for_company_scope_is_unchanged(self):
        """A company-scoped assignment still reports every right on its role."""
        PermissionChecker.assign_role(self.ali, self.role_company_admin, self.company)
        rights = PermissionChecker.rights_for(self.ali, company=self.company)
        self.assertIn("project.create", rights)
        self.assertIn("persona.create", rights)
        self.assertIn("topic.mark_read", rights)


class EdgeCaseTests(PermissionCheckerTestCase):
    """Things that don't map to a single use case above, but matter for correctness."""

    def test_unauthenticated_user_is_always_denied(self):
        from django.contrib.auth.models import AnonymousUser
        self.assertFalse(
            PermissionChecker.can(AnonymousUser(), "project.create", company=self.company)
        )

    def test_unknown_right_code_raises_value_error(self):
        with self.assertRaises(ValueError):
            PermissionChecker.can(self.owner, "not.a.real.right", company=self.company)

    def test_assign_role_is_idempotent(self):
        """Assigning the same role to the same user/scope twice does not create a duplicate row."""
        PermissionChecker.assign_role(self.sara, self.role_company_admin, self.company)
        PermissionChecker.assign_role(self.sara, self.role_company_admin, self.company)
        self.assertEqual(
            RoleAssignment.objects.filter(user=self.sara, role=self.role_company_admin).count(), 1,
        )

    def test_revoke_role_removes_the_assignment(self):
        PermissionChecker.assign_role(self.sara, self.role_company_admin, self.company)
        self.assertTrue(PermissionChecker.can(self.sara, "project.create", company=self.company))

        deleted = PermissionChecker.revoke_role(self.sara, self.role_company_admin, self.company)
        self.assertEqual(deleted, 1)
        self.assertFalse(PermissionChecker.can(self.sara, "project.create", company=self.company))


class UC2_ListVsViewTests(PermissionCheckerTestCase):
    """
    UC2 -- listing the projects a user can see. can() answers "may this
    user act on THIS ONE object" -- it does not, by itself, return a
    filtered list. These tests show what it DOES answer, which is what
    the actual list_projects query needs to branch on: does the user
    hold a company-wide 'project.list' right (see everything), or only
    'project.view' on specific projects they're individually scoped to
    (see just those).
    """

    def setUp(self):
        super().setUp()
        self.r_project_list = Right.objects.create(code="project.list", object_type="project", scope="company")
        self.r_project_view = Right.objects.create(code="project.view", object_type="project", scope="project")
        RoleRight.objects.create(role=self.role_company_admin, right=self.r_project_list)
        RoleRight.objects.create(role=self.role_company_admin, right=self.r_project_view)
        RoleRight.objects.create(role=self.role_project_admin, right=self.r_project_view)

    def test_company_scoped_admin_can_list_company_wide(self):
        PermissionChecker.assign_role(self.sara, self.role_company_admin, self.company)
        self.assertTrue(
            PermissionChecker.can(self.sara, "project.list", company=self.company),
            "Company-scoped Admin should see every project in the company, not just ones they're added to.",
        )

    def test_project_scoped_admin_cannot_list_company_wide_but_can_view_their_own(self):
        PermissionChecker.assign_role(self.ali, self.role_project_admin, self.project)
        self.assertFalse(
            PermissionChecker.can(self.ali, "project.list", company=self.company),
            "A user scoped to one project has no company-wide list right -- "
            "the actual query must fall back to their individual RoleAssignments.",
        )
        self.assertTrue(
            PermissionChecker.can(self.ali, "project.view", obj=self.project),
            "But they can still view the one project they hold a direct assignment on.",
        )
        other_project = Project.objects.create(company=self.company, name="Other", slug="other-uc2")
        self.assertFalse(
            PermissionChecker.can(self.ali, "project.view", obj=other_project),
            "And correctly cannot view a project they were never added to.",
        )


class UC9_SessionCreateCloseTests(PermissionCheckerTestCase):
    """UC9 -- a Topic Member can open and close an AI session in their own topic, and only that one."""

    def setUp(self):
        super().setUp()
        self.r_session_create = Right.objects.create(code="session.create", object_type="session", scope="topic")
        self.r_session_close = Right.objects.create(code="session.close", object_type="session", scope="topic")
        RoleRight.objects.create(role=self.role_topic_member, right=self.r_session_create)
        RoleRight.objects.create(role=self.role_topic_member, right=self.r_session_close)

    def test_topic_member_can_open_and_close_session_on_own_topic(self):
        PermissionChecker.assign_role(self.ali, self.role_topic_member, self.topic_a)
        self.assertTrue(PermissionChecker.can(self.ali, "session.create", obj=self.topic_a))
        self.assertTrue(PermissionChecker.can(self.ali, "session.close", obj=self.topic_a))

    def test_topic_member_cannot_open_session_on_a_topic_they_are_not_in(self):
        PermissionChecker.assign_role(self.ali, self.role_topic_member, self.topic_a)
        self.assertFalse(PermissionChecker.can(self.ali, "session.create", obj=self.topic_b))

    def test_project_scoped_admin_can_open_session_on_any_topic_in_their_project(self):
        # channel_create/topic_mark_read/persona_mention were granted to role_project_admin
        # in the base fixture, but not session rights -- grant them here to prove reach,
        # not default content.
        RoleRight.objects.create(role=self.role_project_admin, right=self.r_session_create)
        PermissionChecker.assign_role(self.sara, self.role_project_admin, self.project)
        self.assertTrue(PermissionChecker.can(self.sara, "session.create", obj=self.topic_a))
        self.assertTrue(PermissionChecker.can(self.sara, "session.create", obj=self.topic_b))


class UC11_ProjectArchiveTests(PermissionCheckerTestCase):
    """
    UC11 -- archiving a project (the reversible soft-delete that replaced
    the old, since-removed project.delete). Unlike the old policy this
    right IS included in DEFAULT_ROLE_RIGHTS["Admin"] (see rights.py),
    reachable by both a Company-scoped Admin and a Project-scoped Admin
    on their own project -- archiving isn't Owner-tier the way deletion
    used to be.
    """

    def setUp(self):
        super().setUp()
        self.r_project_archive = Right.objects.create(code="project.archive", object_type="project", scope="project")
        RoleRight.objects.create(role=self.role_company_admin, right=self.r_project_archive)
        RoleRight.objects.create(role=self.role_project_admin, right=self.r_project_archive)
        # Mirrors rights.py: DEFAULT_ROLE_RIGHTS["Admin"] now includes project.archive,
        # granted identically at both assignment scopes -- see AIResourceTestCase's
        # docstring for why that's the right way to fixture this (reachability is
        # decided by _scope_chain/_SCOPE_ORDER, not by which rights got curated per role).

    def test_company_scoped_admin_can_archive(self):
        PermissionChecker.assign_role(self.sara, self.role_company_admin, self.company)
        self.assertTrue(PermissionChecker.can(self.sara, "project.archive", obj=self.project))

    def test_project_admin_can_archive_their_own_project(self):
        """
        The actual behaviour change vs. the old project.delete policy:
        a Project Admin with no company-wide assignment at all can now
        archive the one project they administer.
        """
        PermissionChecker.assign_role(self.ali, self.role_project_admin, self.project)
        self.assertTrue(PermissionChecker.can(self.ali, "project.archive", obj=self.project))

    def test_project_admin_cannot_archive_a_different_project(self):
        other_project = Project.objects.create(company=self.company, name="Other", slug="other-uc11")
        PermissionChecker.assign_role(self.ali, self.role_project_admin, self.project)
        self.assertFalse(PermissionChecker.can(self.ali, "project.archive", obj=other_project))

    def test_member_cannot_archive(self):
        """role_topic_member never holds project.archive -- Member/Viewer tier never gets it."""
        PermissionChecker.assign_role(self.ali, self.role_topic_member, self.topic_a)
        self.assertFalse(PermissionChecker.can(self.ali, "project.archive", obj=self.project))


class UC18_ChannelTopicArchiveAndIncludeArchivedTests(PermissionCheckerTestCase):
    """
    UC18 -- channel.archive/topic.archive follow the exact same pattern
    as project.archive (UC11), one level down each. Also covers the
    "same right gates the view-archived capability too" design: these
    tests exercise row_rules._with_archived() indirectly via
    visible_projects(..., include_archived=True), which is what actually
    decides who sees an archived object after the fact.
    """

    def setUp(self):
        super().setUp()
        self.r_channel_archive = Right.objects.create(code="channel.archive", object_type="channel", scope="project")
        self.r_topic_archive = Right.objects.create(code="topic.archive", object_type="topic", scope="topic")
        self.r_project_archive = Right.objects.create(code="project.archive", object_type="project", scope="project")
        self.r_project_list = Right.objects.create(code="project.list", object_type="project", scope="company")
        for right in (self.r_channel_archive, self.r_topic_archive, self.r_project_archive, self.r_project_list):
            RoleRight.objects.create(role=self.role_company_admin, right=right)
        RoleRight.objects.create(role=self.role_project_admin, right=self.r_channel_archive)
        RoleRight.objects.create(role=self.role_project_admin, right=self.r_project_archive)

    def test_project_admin_can_archive_own_channel(self):
        PermissionChecker.assign_role(self.ali, self.role_project_admin, self.project)
        self.assertTrue(PermissionChecker.can(self.ali, "channel.archive", obj=self.channel))

    def test_company_admin_can_archive_topic(self):
        PermissionChecker.assign_role(self.sara, self.role_company_admin, self.company)
        self.assertTrue(PermissionChecker.can(self.sara, "topic.archive", obj=self.topic_a))

    def test_project_admin_sees_own_archived_project_with_include_archived(self):
        from .row_rules import visible_projects

        PermissionChecker.assign_role(self.ali, self.role_project_admin, self.project)
        self.project.soft_delete()

        self.assertNotIn(
            self.project, visible_projects(self.ali, self.company),
            "Without include_archived, the archived project stays hidden even from its own admin.",
        )
        self.assertIn(
            self.project, visible_projects(self.ali, self.company, include_archived=True),
            "With include_archived, Ali (Project Admin on this exact project, holding "
            "project.archive on it) sees it again.",
        )

    def test_member_never_sees_archived_project_even_with_include_archived(self):
        from .row_rules import visible_projects

        PermissionChecker.assign_role(self.ali, self.role_topic_member, self.topic_a)
        self.project.soft_delete()

        self.assertNotIn(
            self.project, visible_projects(self.ali, self.company, include_archived=True),
            "Ali holds no project.archive anywhere -- include_archived is a no-op for him, "
            "not a backdoor.",
        )

    def test_project_admin_on_other_project_does_not_see_this_ones_archived_project(self):
        from .row_rules import visible_projects

        other_project = Project.objects.create(company=self.company, name="Other", slug="other-uc18")
        PermissionChecker.assign_role(self.ali, self.role_project_admin, other_project)
        self.project.soft_delete()

        self.assertNotIn(
            self.project, visible_projects(self.ali, self.company, include_archived=True),
            "Ali's project.archive reaches other_project, not self.project -- "
            "per-object check in _with_archived correctly excludes it.",
        )


class AIResourceTestCase(PermissionCheckerTestCase):
    """
    Shared fixture for UC13-17 (Model Config / MCP Server / Persona
    permissions -- see USE_CASES.md). Extends the base fixture with a
    second project (so project-to-project isolation can be tested, same
    idea as UC3/UC17), the Rights these use, and one instance of each
    AI resource type, attached to self.project.

    The Agent half of this fixture is gone -- AIAgent no longer exists,
    so there is no agent object to build and no agent.* right to grant.
    Persona absorbed it: a persona is one ModelConfig, an optional
    advisor, and zero or more MCPServers.

    Rights are granted to role_company_admin AND role_project_admin
    identically, mirroring DEFAULT_ROLE_RIGHTS["Admin"] in rights.py --
    it's the same Role philosophy at two different assignment scopes.
    Whether a right actually becomes reachable is entirely down to
    _scope_chain() + _SCOPE_ORDER, not which rights were curated per
    role here -- e.g. role_project_admin holds the RoleRight for
    model_config.create (COMPANY scope) same as role_company_admin does, but
    a PROJECT-scoped assignment can never reach a COMPANY-scope right
    (see UC6/UC7), so the create test for Project Admin below still
    correctly denies.
    """

    def setUp(self):
        super().setUp()

        self.other_project = Project.objects.create(
            company=self.company, name="Other Project", slug="other-project-ai",
        )

        # agent.list / agent.create / agent.update / agent.delete are NOT
        # created here any more -- those Right rows no longer exist.
        self.r_model_config_list = Right.objects.create(code="model_config.list", object_type="model_config", scope="company")
        self.r_model_config_create = Right.objects.create(code="model_config.create", object_type="model_config", scope="company")
        self.r_model_config_attach = Right.objects.create(code="model_config.attach", object_type="project", scope="project")
        self.r_mcp_list = Right.objects.create(code="mcp_server.list", object_type="mcp_server", scope="company")
        self.r_mcp_create = Right.objects.create(code="mcp_server.create", object_type="mcp_server", scope="project")
        self.r_mcp_update = Right.objects.create(code="mcp_server.update", object_type="mcp_server", scope="project")
        self.r_mcp_delete = Right.objects.create(code="mcp_server.delete", object_type="mcp_server", scope="project")
        self.r_persona_list = Right.objects.create(code="persona.list", object_type="persona", scope="company")

        admin_rights = (
            self.r_model_config_list, self.r_model_config_create, self.r_model_config_attach,
            self.r_mcp_list, self.r_mcp_create, self.r_mcp_update, self.r_mcp_delete,
            self.r_persona_list,
        )
        for right in admin_rights:
            RoleRight.objects.create(role=self.role_company_admin, right=right)
            RoleRight.objects.create(role=self.role_project_admin, right=right)

        # provider is now one of the five real providers and model_id is the
        # BARE model name -- "openai/gpt-test" would be rejected by
        # create_model_config's prefix guard, and qualified_id composes the
        # "provider:model" wire string from the two columns.
        self.model_config = ModelConfig.objects.create(
            company=self.company, name="GPT Test", provider="openai", model_id="gpt-test",
            supports_tools=True,
        )
        self.model_config.projects.add(self.project)

        # No AIAgent fixture -- the model is deleted; a persona with MCP
        # servers attached is what "an agent" means now.

        # Project ownership is a real `project` FK, not a `projects` M2M.
        self.mcp_server = MCPServer.objects.create(
            company=self.company, project=self.project,
            name="Search MCP", server_type="remote", transport="http",
            url="https://example.test/mcp",
        )

        shadow = User.objects.create(username="persona_nova_test", user_type="persona", is_active=True)
        self.persona = Persona.objects.create(
            company=self.company, project=self.project, identity_user=shadow,
            name="Nova", model=self.model_config,
        )


class UC13_AIResourceVisibilityTests(AIResourceTestCase):
    """
    UC13 -- listing AI resources is never a can() 403; it's always a
    filtered queryset from the matching visible_*() row-rule function.
    """

    def test_company_admin_sees_every_resource_broad(self):
        PermissionChecker.assign_role(self.sara, self.role_company_admin, self.company)
        self.assertIn(self.model_config, visible_model_configs(self.sara, self.company))
        # visible_agents() is gone with AIAgent -- nothing to assert here.
        self.assertIn(self.mcp_server, visible_mcp_servers(self.sara, self.company))
        self.assertIn(self.persona, visible_personas(self.sara, self.project))

    def test_project_member_sees_own_projects_resources_narrow(self):
        # Ali holds only a Topic-scoped Member assignment on topic_a, which is
        # inside self.project -- no company-wide right, no direct project
        # assignment either. _reachable_project_ids still resolves self.project
        # via the topic -> project traversal, which is all the narrow path
        # of each visible_*() function needs.
        PermissionChecker.assign_role(self.ali, self.role_topic_member, self.topic_a)
        self.assertIn(self.model_config, visible_model_configs(self.ali, self.company))
        # visible_agents() is gone with AIAgent -- nothing to assert here.
        self.assertIn(self.mcp_server, visible_mcp_servers(self.ali, self.company))
        self.assertIn(self.persona, visible_personas(self.ali, self.project))

    def test_outsider_sees_nothing_not_even_a_403(self):
        # Ali holds no assignment anywhere -- these return empty querysets,
        # never raise, matching "list always 200s" from UC13.
        self.assertNotIn(self.model_config, visible_model_configs(self.ali, self.company))
        # visible_agents() is gone with AIAgent -- nothing to assert here.
        self.assertEqual(visible_mcp_servers(self.ali, self.company).count(), 0)
        self.assertEqual(visible_personas(self.ali, self.project).count(), 0)

    def test_project_admin_on_other_project_does_not_see_this_projects_resources(self):
        PermissionChecker.assign_role(self.sara, self.role_project_admin, self.other_project)
        self.assertNotIn(self.model_config, visible_model_configs(self.sara, self.company))
        # visible_agents() is gone with AIAgent -- nothing to assert here.
        self.assertNotIn(self.mcp_server, visible_mcp_servers(self.sara, self.company))
        self.assertEqual(visible_personas(self.sara, self.project).count(), 0)


class UC14_UC15_ModelConfigCreateVsAttachTests(AIResourceTestCase):
    """
    UC14/15 -- model_config.create (COMPANY scope, touches the API key) is
    Owner/Admin-only regardless of assignment scope; model_config.attach
    (PROJECT scope, never touches the key) is the separate, lighter
    right a Project Admin can also reach.
    """

    def test_company_admin_can_create_model_config(self):
        PermissionChecker.assign_role(self.sara, self.role_company_admin, self.company)
        self.assertTrue(PermissionChecker.can(self.sara, "model_config.create", company=self.company))

    def test_project_admin_cannot_create_model_config(self):
        PermissionChecker.assign_role(self.ali, self.role_project_admin, self.project)
        self.assertFalse(
            PermissionChecker.can(self.ali, "model_config.create", company=self.company),
            "model_config.create is COMPANY scope -- a PROJECT-scoped assignment can never reach it, "
            "even though role_project_admin holds the RoleRight (see class docstring).",
        )

    def test_project_admin_can_attach_existing_config_to_own_project(self):
        PermissionChecker.assign_role(self.ali, self.role_project_admin, self.project)
        self.assertTrue(PermissionChecker.can(self.ali, "model_config.attach", obj=self.project))

    def test_project_admin_cannot_attach_to_a_project_they_do_not_admin(self):
        PermissionChecker.assign_role(self.ali, self.role_project_admin, self.project)
        self.assertFalse(PermissionChecker.can(self.ali, "model_config.attach", obj=self.other_project))

    def test_company_admin_can_attach_too(self):
        # PROJECT reach flows down from COMPANY -- see _SCOPE_ORDER in checker.py.
        PermissionChecker.assign_role(self.sara, self.role_company_admin, self.company)
        self.assertTrue(PermissionChecker.can(self.sara, "model_config.attach", obj=self.project))


class UC16_UC17_McpServerProjectScopeTests(AIResourceTestCase):
    """
    UC16/17 -- mcp_server.* create+update+delete are PROJECT scope: a
    Project Admin reaches them on their own project (and the MCPServer
    objects within it, via _scope_chain reading the `project` FK), but
    not on a project they don't administer.

    The agent.* half of this class is gone -- AIAgent no longer exists,
    so there are no agent.create/update/delete rights left to test.
    """

    def test_project_admin_can_create_mcp_server_in_own_project(self):
        PermissionChecker.assign_role(self.ali, self.role_project_admin, self.project)
        self.assertTrue(PermissionChecker.can(self.ali, "mcp_server.create", obj=self.project))

    def test_project_admin_can_update_and_delete_own_projects_mcp_server(self):
        PermissionChecker.assign_role(self.ali, self.role_project_admin, self.project)
        self.assertTrue(PermissionChecker.can(self.ali, "mcp_server.update", obj=self.mcp_server))
        self.assertTrue(PermissionChecker.can(self.ali, "mcp_server.delete", obj=self.mcp_server))

    def test_project_admin_cannot_touch_another_projects_mcp_server(self):
        # Ownership is set at construction now -- a server belongs to exactly
        # one project and is not transferable, so there is no .add() step.
        other_mcp = MCPServer.objects.create(
            company=self.company, project=self.other_project,
            name="Other MCP", server_type="remote", transport="http",
            url="https://example.test/other",
        )
        PermissionChecker.assign_role(self.ali, self.role_project_admin, self.project)
        self.assertFalse(PermissionChecker.can(self.ali, "mcp_server.update", obj=other_mcp))
        self.assertFalse(PermissionChecker.can(self.ali, "mcp_server.delete", obj=other_mcp))

    def test_company_admin_can_manage_mcp_server_in_any_project(self):
        PermissionChecker.assign_role(self.sara, self.role_company_admin, self.company)
        self.assertTrue(PermissionChecker.can(self.sara, "mcp_server.delete", obj=self.mcp_server))

    def test_unsaved_mcp_server_falls_back_to_company_only_scope(self):
        """
        MCPServer.project is NOT NULL now, so "no project attached yet" can
        only mean an in-memory instance that was never saved. _scope_chain's
        project_id guard then falls through to the plain company_id
        fallback, meaning only a COMPANY-scoped assignment reaches it.

        The AIAgent variant of this case went away with the model.
        """
        unsaved = MCPServer(
            company=self.company, name="Orphan", server_type="remote",
            transport="http", url="https://example.test/orphan",
        )
        PermissionChecker.assign_role(self.ali, self.role_project_admin, self.project)
        self.assertFalse(PermissionChecker.can(self.ali, "mcp_server.delete", obj=unsaved))

        PermissionChecker.assign_role(self.sara, self.role_company_admin, self.company)
        self.assertTrue(PermissionChecker.can(self.sara, "mcp_server.delete", obj=unsaved))


class MyPermissionsPayloadTests(PermissionCheckerTestCase):
    """
    The payload behind GET /api/v1/me/permissions/ -- what the web app draws
    every management control from.
    """

    def setUp(self):
        super().setUp()
        # row_rules asks can() for these three, and can() raises on an
        # unregistered code -- the base fixture only seeds what IT exercises.
        self.r_project_list = Right.objects.create(code="project.list", object_type="project", scope="company")
        self.r_channel_list = Right.objects.create(code="channel.list", object_type="channel", scope="project")
        self.r_topic_list = Right.objects.create(code="topic.list", object_type="topic", scope="project")

    def _payload(self, user):
        from authn.services import my_permissions
        return my_permissions(user, self.company)

    def test_project_scoped_admin_gets_their_project_despite_no_company_role(self):
        """
        The bug this endpoint exists to fix: CompanyAccess.role is 'member',
        so the old UI hid every control, while the server would have accepted
        the request.
        """
        PermissionChecker.assign_role(self.sara, self.role_project_admin, self.project)
        payload = self._payload(self.sara)

        self.assertEqual(payload["company"]["rights"], [])
        self.assertIn(str(self.project.id), payload["projects"])
        self.assertIn("channel.create", payload["projects"][str(self.project.id)])

    def test_a_topic_reached_only_through_the_project_still_gets_a_key(self):
        """
        The client does a flat lookup and never walks the hierarchy, so an
        unemitted topic silently hides every TOPIC-scoped control from exactly
        the project admin this endpoint is for.
        """
        # channel.list / topic.list are what row_rules uses to widen the view.
        RoleRight.objects.create(role=self.role_project_admin, right=self.r_channel_list)
        RoleRight.objects.create(role=self.role_project_admin, right=self.r_topic_list)

        PermissionChecker.assign_role(self.sara, self.role_project_admin, self.project)
        payload = self._payload(self.sara)

        # Both topics live under the project, and she holds no topic-scoped
        # assignment at all -- they must still be keyed, with their rights.
        self.assertIn(str(self.topic_a.id), payload["topics"])
        self.assertIn(str(self.topic_b.id), payload["topics"])
        self.assertIn("persona.mention", payload["topics"][str(self.topic_a.id)])
        self.assertIn("topic.mark_read", payload["topics"][str(self.topic_a.id)])

    def test_topic_scoped_member_gets_only_their_own_topic(self):
        PermissionChecker.assign_role(self.ali, self.role_topic_member, self.topic_a)
        payload = self._payload(self.ali)

        self.assertIn(str(self.topic_a.id), payload["topics"])
        self.assertNotIn(str(self.topic_b.id), payload["topics"])
        # The project surfaces as a navigation waypoint, carrying no rights.
        self.assertEqual(payload["projects"].get(str(self.project.id)), [])

    def test_a_user_with_nothing_gets_empty_everything(self):
        payload = self._payload(self.ali)
        self.assertEqual(payload["company"]["rights"], [])
        self.assertEqual(payload["projects"], {})
        self.assertEqual(payload["topics"], {})

    def test_payload_never_reports_a_right_can_would_deny(self):
        """The invariant the whole design rests on."""
        PermissionChecker.assign_role(self.ali, self.role_topic_member, self.topic_a)
        payload = self._payload(self.ali)
        for code in payload["topics"].get(str(self.topic_a.id), []):
            self.assertTrue(
                PermissionChecker.can(self.ali, code, obj=self.topic_a),
                f"payload claims {code} but can() denies it",
            )


class PayloadMatchesCanExhaustivelyTests(TestCase):
    """
    The invariant the endpoint rests on, checked by brute force against the
    REAL registry and the REAL seeded roles: for every user, every object and
    every right, the payload contains the right if and only if can() grants it.

    Both directions matter. A right the payload claims but can() denies draws a
    button that 403s. A right can() grants but the payload omits hides a
    control the user is entitled to -- the exact bug class this work exists to
    fix, just moved one layer along.
    """

    def setUp(self):
        from authn.permissions.rights import DEFAULT_ROLE_RIGHTS, REGISTRY

        self.company = Company.objects.create(name="Acme", slug="acme")
        self.owner_user = User.objects.create_user(username="o", email="o@acme.test", password="x")
        self.company.owner = self.owner_user
        self.company.save(update_fields=["owner"])

        self.project_a = Project.objects.create(company=self.company, name="A", slug="a")
        self.project_b = Project.objects.create(company=self.company, name="B", slug="b")
        self.channel_a = Channel.objects.create(company=self.company, project=self.project_a, name="g", slug="g")
        self.channel_b = Channel.objects.create(company=self.company, project=self.project_b, name="g", slug="g-b")
        self.topic_a1 = ChatTopic.objects.create(company=self.company, project=self.project_a, channel=self.channel_a, title="A1", slug="a1")
        self.topic_a2 = ChatTopic.objects.create(company=self.company, project=self.project_a, channel=self.channel_a, title="A2", slug="a2")
        self.topic_b1 = ChatTopic.objects.create(company=self.company, project=self.project_b, channel=self.channel_b, title="B1", slug="b1")

        # The real registry and the real default roles -- same rows
        # seed_permissions would create.
        by_code = {}
        for code, object_type, scope, description in REGISTRY:
            by_code[code] = Right.objects.create(
                code=code, object_type=object_type, scope=scope, description=description,
            )
        self.all_codes = list(by_code)
        self.roles = {}
        for name, codes in DEFAULT_ROLE_RIGHTS.items():
            role = Role.objects.create(company=self.company, name=name, scope="company")
            for code in codes:
                RoleRight.objects.create(role=role, right=by_code[code])
            self.roles[name] = role

        # Six shapes of user, covering every scope an assignment can sit at.
        def mk(username):
            return User.objects.create_user(username=username, email=f"{username}@acme.test", password="x")

        self.people = {}
        self.people["owner"] = mk("p_owner")
        PermissionChecker.assign_role(self.people["owner"], self.roles["Owner"], self.company)
        self.people["company_admin"] = mk("p_cadmin")
        PermissionChecker.assign_role(self.people["company_admin"], self.roles["Admin"], self.company)
        self.people["company_member"] = mk("p_cmember")
        PermissionChecker.assign_role(self.people["company_member"], self.roles["Member"], self.company)
        self.people["company_viewer"] = mk("p_cviewer")
        PermissionChecker.assign_role(self.people["company_viewer"], self.roles["Viewer"], self.company)
        # The case the whole change exists for: Admin on ONE project only.
        self.people["project_admin"] = mk("p_padmin")
        PermissionChecker.assign_role(self.people["project_admin"], self.roles["Admin"], self.project_a)
        # Member on ONE topic only.
        self.people["topic_member"] = mk("p_tmember")
        PermissionChecker.assign_role(self.people["topic_member"], self.roles["Member"], self.topic_a1)
        # Stacked: Viewer company-wide PLUS Admin on one project.
        self.people["viewer_plus_project_admin"] = mk("p_stacked")
        PermissionChecker.assign_role(self.people["viewer_plus_project_admin"], self.roles["Viewer"], self.company)
        PermissionChecker.assign_role(self.people["viewer_plus_project_admin"], self.roles["Admin"], self.project_a)
        # Holds nothing at all.
        self.people["outsider"] = mk("p_outsider")

    def _expected(self, user, **kwargs):
        return {code for code in self.all_codes if PermissionChecker.can(user, code, **kwargs)}

    def test_payload_equals_can_for_every_user_and_object(self):
        from authn.services import my_permissions

        for label, user in self.people.items():
            payload = my_permissions(user, self.company)

            with self.subTest(user=label, obj="company"):
                self.assertEqual(
                    set(payload["company"]["rights"]),
                    self._expected(user, company=self.company),
                )

            for project in (self.project_a, self.project_b):
                key = str(project.id)
                if key not in payload["projects"]:
                    continue  # not visible -- covered by the visibility tests
                with self.subTest(user=label, obj=f"project:{project.name}"):
                    self.assertEqual(
                        set(payload["projects"][key]),
                        self._expected(user, obj=project),
                    )

            for topic in (self.topic_a1, self.topic_a2, self.topic_b1):
                key = str(topic.id)
                if key not in payload["topics"]:
                    continue
                with self.subTest(user=label, obj=f"topic:{topic.title}"):
                    self.assertEqual(
                        set(payload["topics"][key]),
                        self._expected(user, obj=topic),
                    )

    def test_every_object_a_user_can_act_on_is_keyed(self):
        """
        The converse of the visibility filter: if can() grants ANY right on an
        object, that object must appear in the payload -- otherwise the client's
        flat lookup silently hides a control the user is entitled to.
        """
        from authn.services import my_permissions

        for label, user in self.people.items():
            payload = my_permissions(user, self.company)
            for project in (self.project_a, self.project_b):
                if self._expected(user, obj=project):
                    with self.subTest(user=label, obj=f"project:{project.name}"):
                        self.assertIn(str(project.id), payload["projects"])
            for topic in (self.topic_a1, self.topic_a2, self.topic_b1):
                if self._expected(user, obj=topic):
                    with self.subTest(user=label, obj=f"topic:{topic.title}"):
                        self.assertIn(str(topic.id), payload["topics"])
