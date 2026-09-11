"""
workspace/tests.py

Invites that carry grants: who ends up with which RoleAssignment, at which
scope, through every path that can hand one out -- and that the permission
payload the app gates on reports exactly that afterwards.
"""
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from authn.permissions.checker import PermissionChecker
from authn.permissions.models import Role, RoleAssignment
from authn.services import auth_verify, my_permissions
from nucleus.models import (
    ChatTopic, Channel, Company, CompanyAccess, Invitation, Project, ProjectMember, TopicParticipant,
)
from workspace.services import apply_grants, invite_to_project, invite_to_system

User = get_user_model()


class InviteGrantsFixture(TestCase):
    """
    One company with the four default roles, two projects -- Alpha with two
    channels and three topics, Beta with nothing in it -- an owner, and Sara,
    an existing member with server access only.
    """

    def setUp(self):
        self.company = Company.objects.create(name="Acme", slug="acme")
        self.owner = User.objects.create_user(username="owner", email="owner@acme.test", password="x")
        self.company.owner = self.owner
        self.company.save(update_fields=["owner"])
        CompanyAccess.objects.create(company=self.company, user=self.owner, role="owner")
        # The real registry and default bundles -- my_permissions() walks the
        # row rules, which check rights by code and refuse unknown ones.
        call_command("seed_permissions", stdout=StringIO(), stderr=StringIO())
        self.member_role = Role.objects.get(company=self.company, name="Member")

        self.p1 = Project.objects.create(company=self.company, name="Alpha", slug="alpha")
        self.c1 = Channel.objects.create(company=self.company, project=self.p1, name="general", slug="general")
        self.c2 = Channel.objects.create(company=self.company, project=self.p1, name="design", slug="design")
        self.t1 = ChatTopic.objects.create(company=self.company, project=self.p1, channel=self.c1, title="t1", slug="t1")
        self.t2 = ChatTopic.objects.create(company=self.company, project=self.p1, channel=self.c1, title="t2", slug="t2")
        self.t3 = ChatTopic.objects.create(company=self.company, project=self.p1, channel=self.c2, title="t3", slug="t3")
        self.p2 = Project.objects.create(company=self.company, name="Beta", slug="beta")
        # Never granted to anyone -- the project a scoped invitee must NOT see.
        self.p3 = Project.objects.create(company=self.company, name="Gamma", slug="gamma")

        self.sara = User.objects.create_user(username="sara", email="sara@acme.test", password="x")
        CompanyAccess.objects.create(company=self.company, user=self.sara, role="member", invited_by=self.owner)
        PermissionChecker.assign_role(self.sara, self.member_role, self.company, granted_by=self.owner)

    def scopes(self, user) -> set:
        """Every (scope type, object id) this user holds a role at."""
        return {(a.scope_object_type, str(a.scope_object_id)) for a in RoleAssignment.objects.filter(user=user)}

    def whole(self, project):
        return {"project_id": str(project.id), "topic_ids": []}

    def only(self, project, *topics):
        return {"project_id": str(project.id), "topic_ids": [str(t.id) for t in topics]}


class ApplyGrantsTests(InviteGrantsFixture):
    def test_a_whole_project_is_one_project_scope_assignment(self):
        applied = apply_grants(self.company, self.sara, [self.whole(self.p1)], "member", self.owner)
        self.assertEqual(applied, [self.whole(self.p1)])
        self.assertIn(("project", str(self.p1.id)), self.scopes(self.sara))
        self.assertFalse(any(kind == "topic" for kind, _ in self.scopes(self.sara)))
        self.assertTrue(ProjectMember.objects.filter(project=self.p1, user=self.sara, is_active=True).exists())

    def test_topics_are_topic_scope_assignments_and_never_the_project(self):
        apply_grants(self.company, self.sara, [self.only(self.p1, self.t1, self.t3)], "member", self.owner)
        held = self.scopes(self.sara)
        self.assertIn(("topic", str(self.t1.id)), held)
        self.assertIn(("topic", str(self.t3.id)), held)
        self.assertNotIn(("topic", str(self.t2.id)), held)
        self.assertNotIn(("project", str(self.p1.id)), held)
        # The legacy rows the rest of the app still reads.
        self.assertTrue(ProjectMember.objects.filter(project=self.p1, user=self.sara).exists())
        self.assertEqual(TopicParticipant.objects.filter(user=self.sara).count(), 2)

    def test_several_projects_in_one_call(self):
        applied = apply_grants(
            self.company, self.sara, [self.only(self.p1, self.t2), self.whole(self.p2)], "member", self.owner,
        )
        self.assertEqual(len(applied), 2)
        held = self.scopes(self.sara)
        self.assertIn(("topic", str(self.t2.id)), held)
        self.assertIn(("project", str(self.p2.id)), held)

    def test_is_idempotent(self):
        grants = [self.only(self.p1, self.t1), self.whole(self.p2)]
        apply_grants(self.company, self.sara, grants, "member", self.owner)
        before = (RoleAssignment.objects.count(), ProjectMember.objects.count(), TopicParticipant.objects.count())
        apply_grants(self.company, self.sara, grants, "member", self.owner)
        after = (RoleAssignment.objects.count(), ProjectMember.objects.count(), TopicParticipant.objects.count())
        self.assertEqual(before, after)

    def test_the_same_project_listed_twice_merges_and_whole_wins(self):
        applied = apply_grants(
            self.company, self.sara, [self.only(self.p1, self.t1), self.whole(self.p1)], "member", self.owner,
        )
        self.assertEqual(applied, [self.whole(self.p1)])
        self.assertIn(("project", str(self.p1.id)), self.scopes(self.sara))
        self.assertNotIn(("topic", str(self.t1.id)), self.scopes(self.sara))

    def test_refuses_an_unknown_project_before_writing_anything(self):
        with self.assertRaises(ValueError):
            apply_grants(
                self.company, self.sara,
                [self.whole(self.p1), {"project_id": "00000000-0000-0000-0000-000000000000", "topic_ids": []}],
                "member", self.owner,
            )
        self.assertNotIn(("project", str(self.p1.id)), self.scopes(self.sara))

    def test_refuses_a_topic_from_another_project(self):
        with self.assertRaisesRegex(ValueError, "not found in project 'Beta'"):
            apply_grants(self.company, self.sara, [self.only(self.p2, self.t1)], "member", self.owner)

    def test_refuses_a_malformed_id(self):
        with self.assertRaises(ValueError):
            apply_grants(self.company, self.sara, [{"project_id": "not-a-uuid", "topic_ids": []}], "member", self.owner)
        with self.assertRaises(ValueError):
            apply_grants(self.company, self.sara, [{"project_id": str(self.p1.id), "topic_ids": ["nope"]}], "member", self.owner)

    def test_not_strict_skips_what_is_gone_and_applies_the_rest(self):
        self.p2.soft_delete()
        applied = apply_grants(
            self.company, self.sara, [self.whole(self.p2), self.only(self.p1, self.t1)], "member", self.owner, strict=False,
        )
        self.assertEqual(applied, [self.only(self.p1, self.t1)])
        self.assertNotIn(("project", str(self.p2.id)), self.scopes(self.sara))

    def test_not_strict_never_widens_a_topic_list_whose_topics_are_gone(self):
        self.t1.soft_delete()
        applied = apply_grants(self.company, self.sara, [self.only(self.p1, self.t1)], "member", self.owner, strict=False)
        self.assertEqual(applied, [])
        self.assertNotIn(("project", str(self.p1.id)), self.scopes(self.sara))

    def test_an_archived_topic_is_refused_when_strict(self):
        self.t1.soft_delete()
        with self.assertRaises(ValueError):
            apply_grants(self.company, self.sara, [self.only(self.p1, self.t1)], "member", self.owner)

    def test_a_topic_listed_twice_is_one_assignment(self):
        applied = apply_grants(self.company, self.sara, [self.only(self.p1, self.t1, self.t1)], "member", self.owner)
        self.assertEqual(applied, [self.only(self.p1, self.t1)])
        self.assertEqual(RoleAssignment.objects.filter(user=self.sara, scope_object_type="topic").count(), 1)

    def test_grants_add_to_what_a_narrow_member_already_holds(self):
        bob = User.objects.create_user(username="bob", email="bob@acme.test", password="x")
        CompanyAccess.objects.create(company=self.company, user=bob, role="member", invited_by=self.owner)
        apply_grants(self.company, bob, [self.only(self.p1, self.t1)], "member", self.owner)
        apply_grants(self.company, bob, [self.whole(self.p2)], "member", self.owner)
        self.assertEqual(self.scopes(bob), {("topic", str(self.t1.id)), ("project", str(self.p2.id))})


class InviteToSystemGrantsTests(InviteGrantsFixture):
    def test_an_existing_member_gets_the_grants_at_once(self):
        r = invite_to_system(self.company, self.owner, "sara@acme.test", role="member", grants=[self.only(self.p1, self.t1)])
        self.assertFalse(r["is_new_user"])
        self.assertEqual(r["grants"], [self.only(self.p1, self.t1)])
        self.assertIn("1 topic", r["message"])
        self.assertIn(("topic", str(self.t1.id)), self.scopes(self.sara))

    def test_a_known_user_not_yet_a_member_gets_membership_and_the_grants(self):
        bob = User.objects.create_user(username="bob", email="bob@acme.test", password="x")
        r = invite_to_system(self.company, self.owner, "bob@acme.test", role="viewer", grants=[self.whole(self.p2)])
        self.assertEqual(r["grants"], [self.whole(self.p2)])
        self.assertTrue(CompanyAccess.objects.filter(company=self.company, user=bob, role="viewer").exists())
        # Scoped: the role lands on Beta only -- no company-scope assignment,
        # which would reach every project and undo the scoping.
        self.assertEqual(self.scopes(bob), {("project", str(self.p2.id))})

    def test_a_known_user_invited_server_wide_gets_the_company_scope_role(self):
        bob = User.objects.create_user(username="bob", email="bob@acme.test", password="x")
        invite_to_system(self.company, self.owner, "bob@acme.test", role="viewer")
        self.assertEqual(self.scopes(bob), {("company", str(self.company.id))})

    def test_a_brand_new_person_gets_the_grants_stored_for_acceptance(self):
        grants = [self.only(self.p1, self.t1, self.t3), self.whole(self.p2)]
        r = invite_to_system(self.company, self.owner, "new@acme.test", role="member", grants=grants)
        self.assertTrue(r["is_new_user"])
        self.assertEqual(r["grants"], grants)
        invitation = Invitation.objects.get(company=self.company, email="new@acme.test")
        self.assertEqual(invitation.access_payload, {"grants": grants})
        self.assertFalse(RoleAssignment.objects.filter(user__email="new@acme.test").exists())

    def test_a_bad_grant_refuses_the_whole_invite(self):
        with self.assertRaises(ValueError):
            invite_to_system(self.company, self.owner, "new@acme.test", grants=[self.only(self.p2, self.t1)])
        self.assertFalse(Invitation.objects.filter(email="new@acme.test").exists())

    def test_without_grants_the_outcome_is_unchanged(self):
        r = invite_to_system(self.company, self.owner, "sara@acme.test")
        self.assertEqual(r["message"], "sara@acme.test is already a member of this server.")
        self.assertEqual(r["grants"], [])
        r = invite_to_system(self.company, self.owner, "new@acme.test")
        self.assertEqual(Invitation.objects.get(email="new@acme.test").access_payload, {})


class AcceptanceTests(InviteGrantsFixture):
    """The half the owner asked to see proven: after accepting, the person holds exactly what was chosen."""

    def accept(self, email: str) -> User:
        with patch("authn.services.verify_supabase_token", return_value={"email": email}):
            auth_verify("a-supabase-jwt")
        return User.objects.get(email=email)

    def test_a_new_user_holds_exactly_the_invited_scopes_after_accepting(self):
        invite_to_system(
            self.company, self.owner, "new@acme.test", role="member",
            grants=[self.only(self.p1, self.t1, self.t3), self.whole(self.p2)],
        )
        user = self.accept("new@acme.test")
        # Exactly the chosen scopes -- and no company-scope role, which would
        # reach every project and make the choice meaningless.
        self.assertEqual(self.scopes(user), {
            ("topic", str(self.t1.id)),
            ("topic", str(self.t3.id)),
            ("project", str(self.p2.id)),
        })
        self.assertTrue(CompanyAccess.objects.filter(company=self.company, user=user, role="member").exists())
        self.assertEqual(Invitation.objects.get(email="new@acme.test").status, Invitation.Status.ACCEPTED)
        self.assertEqual(set(ProjectMember.objects.filter(user=user).values_list("project_id", flat=True)), {self.p1.id, self.p2.id})
        self.assertEqual(set(TopicParticipant.objects.filter(user=user).values_list("topic_id", flat=True)), {self.t1.id, self.t3.id})

    def test_the_permissions_payload_then_keys_exactly_those_objects(self):
        invite_to_system(
            self.company, self.owner, "new@acme.test", role="member",
            grants=[self.only(self.p1, self.t1, self.t3), self.whole(self.p2)],
        )
        user = self.accept("new@acme.test")
        perms = my_permissions(user, self.company)
        # Gamma exists and was never granted: it must be absent, not just the
        # granted ones present.
        self.assertEqual(set(perms["projects"]), {str(self.p1.id), str(self.p2.id)})
        # t2 shares a channel with t1 but was not granted -- a topic-only grant stays narrow.
        self.assertEqual(set(perms["topics"]), {str(self.t1.id), str(self.t3.id)})
        # Nothing company-wide: no creating projects, no managing people.
        self.assertEqual(perms["company"]["rights"], [])

    def test_the_invitee_can_open_their_topic_and_not_a_sibling(self):
        from types import SimpleNamespace
        from ninja.errors import HttpError
        from chat.api import _resolve_topic_sync

        invite_to_system(self.company, self.owner, "new@acme.test", role="member", grants=[self.only(self.p1, self.t1)])
        user = self.accept("new@acme.test")
        request = SimpleNamespace(auth=user)
        _, _, project, channel, topic = _resolve_topic_sync(request, str(self.p1.id), str(self.c1.id), str(self.t1.id))
        self.assertEqual((project.id, channel.id, topic.id), (self.p1.id, self.c1.id, self.t1.id))
        # t2 sits in the same channel; the invite did not name it.
        with self.assertRaises(HttpError):
            _resolve_topic_sync(request, str(self.p1.id), str(self.c1.id), str(self.t2.id))
        # Beta was not named at all.
        with self.assertRaises(HttpError):
            _resolve_topic_sync(request, str(self.p2.id), str(self.c1.id), str(self.t1.id))

    def test_an_invitation_from_before_grants_existed_still_applies(self):
        Invitation.objects.create(
            company=self.company, email="old@acme.test", role="member", invited_by=self.owner,
            token_hash="legacy", access_payload={"project_id": str(self.p1.id), "scope": "topic", "topic_id": str(self.t2.id)},
        )
        user = self.accept("old@acme.test")
        self.assertEqual(self.scopes(user), {("topic", str(self.t2.id))})

    def test_a_project_archived_after_the_invite_does_not_break_acceptance(self):
        invite_to_system(
            self.company, self.owner, "new@acme.test", role="member",
            grants=[self.whole(self.p2), self.only(self.p1, self.t1)],
        )
        self.p2.soft_delete()
        user = self.accept("new@acme.test")
        self.assertIn(("topic", str(self.t1.id)), self.scopes(user))
        self.assertNotIn(("project", str(self.p2.id)), self.scopes(user))

    def test_a_server_only_invite_grants_nothing_beyond_the_company(self):
        invite_to_system(self.company, self.owner, "new@acme.test", role="viewer")
        user = self.accept("new@acme.test")
        self.assertEqual(self.scopes(user), {("company", str(self.company.id))})

    def test_a_whole_project_invitee_sees_every_topic_in_it_including_later_ones(self):
        invite_to_system(self.company, self.owner, "new@acme.test", role="member", grants=[self.whole(self.p1)])
        user = self.accept("new@acme.test")
        later = ChatTopic.objects.create(company=self.company, project=self.p1, channel=self.c2, title="later", slug="later")
        perms = my_permissions(user, self.company)
        self.assertEqual(set(perms["projects"]), {str(self.p1.id)})
        self.assertEqual(set(perms["topics"]), {str(t.id) for t in (self.t1, self.t2, self.t3, later)})
        self.assertIn("topic.create", perms["projects"][str(self.p1.id)])

    def test_a_topic_only_invitee_can_act_in_their_topic_and_nowhere_else(self):
        invite_to_system(self.company, self.owner, "new@acme.test", role="member", grants=[self.only(self.p1, self.t1)])
        user = self.accept("new@acme.test")
        perms = my_permissions(user, self.company)
        self.assertIn("persona.mention", perms["topics"][str(self.t1.id)])
        self.assertNotIn(str(self.t2.id), perms["topics"])
        # Project-scope rights do not flow up from a topic: no new topics or channels.
        self.assertNotIn("topic.create", perms["projects"][str(self.p1.id)])
        self.assertNotIn("channel.create", perms["projects"][str(self.p1.id)])

    def test_a_scoped_admin_manages_their_project_and_nothing_company_wide(self):
        invite_to_system(self.company, self.owner, "new@acme.test", role="admin", grants=[self.whole(self.p1)])
        user = self.accept("new@acme.test")
        perms = my_permissions(user, self.company)
        for right in ("channel.create", "topic.create", "persona.create", "project.archive"):
            self.assertIn(right, perms["projects"][str(self.p1.id)])
        self.assertEqual(perms["company"]["rights"], [])
        self.assertNotIn(str(self.p2.id), perms["projects"])

    def test_inviting_an_existing_member_with_grants_leaves_their_server_role_alone(self):
        invite_to_system(self.company, self.owner, "sara@acme.test", role="admin", grants=[self.whole(self.p1)])
        self.assertEqual(CompanyAccess.objects.get(company=self.company, user=self.sara).role, "member")
        admin = Role.objects.get(company=self.company, name="Admin")
        self.assertTrue(RoleAssignment.objects.filter(user=self.sara, role=admin, scope_object_id=self.p1.id).exists())


class InviteApiTests(InviteGrantsFixture):
    """The HTTP layer: the request schema takes grants and the response echoes them."""

    def post(self, body: dict):
        from django.test import Client
        # The route's legacy has_perm("add_invitation") gate is not what is
        # under test; a superuser passes it without the Django group setup.
        self.owner.is_superuser = True
        self.owner.save(update_fields=["is_superuser"])
        with patch("authn.auth.verify_supabase_token", return_value={"email": self.owner.email}):
            return Client().post(
                "/api/v1/members/invite/", data=body, content_type="application/json", HTTP_AUTHORIZATION="Bearer t",
            )

    def test_grants_round_trip_through_the_endpoint(self):
        grants = [self.only(self.p1, self.t1), self.whole(self.p2)]
        r = self.post({"email": "new@acme.test", "role": "member", "grants": grants})
        self.assertEqual(r.status_code, 200, r.content)
        body = r.json()
        self.assertTrue(body["is_new_user"])
        self.assertEqual(body["grants"], grants)
        self.assertEqual(Invitation.objects.get(email="new@acme.test").access_payload, {"grants": grants})

    def test_a_bad_grant_is_a_400_with_the_reason_and_nothing_stored(self):
        r = self.post({"email": "new@acme.test", "grants": [self.only(self.p2, self.t1)]})
        self.assertEqual(r.status_code, 400, r.content)
        self.assertIn("not found in project 'Beta'", r.json()["detail"])
        self.assertFalse(Invitation.objects.filter(email="new@acme.test").exists())

    def test_an_old_client_payload_still_works_and_reads_as_server_wide(self):
        r = self.post({"email": "new@acme.test", "role": "viewer"})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["grants"], [])
        self.assertEqual(Invitation.objects.get(email="new@acme.test").access_payload, {})


class InviteToProjectTests(InviteGrantsFixture):
    """The composer's /invite: one topic (or the project), idempotent, through the same helper."""

    def test_a_topic_invite_for_an_existing_member_adds_only_that_topic(self):
        r = invite_to_project(
            self.company, self.owner, self.p1, email="sara@acme.test", scope="topic", topic_id=str(self.t1.id), role="member",
        )
        self.assertEqual(r["scope"], "topic")
        held = self.scopes(self.sara)
        self.assertIn(("topic", str(self.t1.id)), held)
        self.assertNotIn(("project", str(self.p1.id)), held)
        self.assertTrue(TopicParticipant.objects.filter(topic=self.t1, user=self.sara).exists())
        self.assertTrue(ProjectMember.objects.filter(project=self.p1, user=self.sara).exists())

    def test_inviting_someone_already_in_the_topic_changes_nothing(self):
        kwargs = dict(email="sara@acme.test", scope="topic", topic_id=str(self.t1.id), role="member")
        invite_to_project(self.company, self.owner, self.p1, **kwargs)
        before = (RoleAssignment.objects.count(), TopicParticipant.objects.count(), ProjectMember.objects.count())
        r = invite_to_project(self.company, self.owner, self.p1, **kwargs)
        self.assertTrue(r["ok"])
        after = (RoleAssignment.objects.count(), TopicParticipant.objects.count(), ProjectMember.objects.count())
        self.assertEqual(before, after)

    def test_a_project_scope_invite_adds_the_whole_project(self):
        invite_to_project(self.company, self.owner, self.p1, email="sara@acme.test", scope="project", role="member")
        self.assertIn(("project", str(self.p1.id)), self.scopes(self.sara))

    def test_an_unknown_topic_is_refused_rather_than_silently_granting_nothing(self):
        with self.assertRaises(ValueError):
            invite_to_project(
                self.company, self.owner, self.p1, email="sara@acme.test", scope="topic",
                topic_id="00000000-0000-0000-0000-000000000000", role="member",
            )

    def test_a_brand_new_person_gets_the_single_grant_stored(self):
        r = invite_to_project(
            self.company, self.owner, self.p1, email="new@acme.test", scope="topic", topic_id=str(self.t1.id), role="member",
        )
        self.assertTrue(r["is_new_user"])
        self.assertEqual(
            Invitation.objects.get(email="new@acme.test").access_payload,
            {"grants": [self.only(self.p1, self.t1)]},
        )
