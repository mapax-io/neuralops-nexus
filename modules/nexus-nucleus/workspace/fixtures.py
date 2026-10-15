"""
The base test fixture, in a module of its own (Step 2 garbage removal).

It used to live in workspace/tests.py, which imported chat/tests.py at its
bottom while chat/tests.py imported it back at its top — a circle that only
resolved when workspace loaded first, so which tests passed depended on
import ORDER. Now both test files import this module and the circle is gone.
"""
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from authn.permissions.checker import PermissionChecker
from authn.permissions.models import RoleAssignment, Role
from nucleus.models import Channel, ChatTopic, Company, CompanyAccess, Project

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
        PermissionChecker.assign_role(self.owner, Role.objects.get(company=self.company, name="Owner"), self.company, granted_by=self.owner)

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
