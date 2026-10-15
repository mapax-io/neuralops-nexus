"""
Step 6, Part B — the configure fence (change 13.3) + stored tool lists
(change 6).

Every project is born with its reserved "configure" topic; exactly the four
admin-tier roles see it, on every road (lists, single-topic resolve, the bulk
ids helper, the messages API); a direct topic invite does not pierce the
fence. MCP server rows store their tool list, fetched through the engine at
attach/save and from the Refresh button, and ship it to the engine.
"""
from unittest.mock import patch

from authn.permissions.checker import PermissionChecker
from authn.permissions.models import Role
from authn.permissions.row_rules import visible_topic, visible_topic_ids, visible_topics
from chat.tests import MentionRightFixture
from nucleus.models import Channel, ChatTopic, CompanyAccess, MCPServer, User
from workspace import services as ws_svc


class ConfigureFenceTests(MentionRightFixture):
    def setUp(self):
        super().setUp()
        self.delta = ws_svc.create_project(self.company, self.owner, "Delta")
        self.general = Channel.objects.get(project=self.delta, slug="general")
        self.configure = ChatTopic.objects.get(project=self.delta, is_configure=True)

    def titles(self, user):
        return [t.title for t in visible_topics(user, self.general)]

    def test_a_new_project_is_born_with_its_configure_topic(self):
        self.assertEqual(self.configure.title, "configure")
        self.assertEqual(self.configure.slug, "configure")
        self.assertTrue(self.configure.is_active)

    def test_only_the_four_roles_see_it(self):
        self.assertIn("configure", self.titles(self.owner))       # company owner
        self.assertNotIn("configure", self.titles(self.sara))     # Member
        self.assertNotIn("configure", self.titles(self.vera))     # Viewer

        # A PROJECT-level admin is one of the four.
        pat = User.objects.create_user(username="pat6", email="pat6@acme.test", password="x")
        CompanyAccess.objects.create(company=self.company, user=pat, role="member", invited_by=self.owner)
        PermissionChecker.assign_role(
            pat, Role.objects.get(company=self.company, name="Admin"), self.delta, granted_by=self.owner)
        self.assertIn("configure", self.titles(pat))

    def test_the_fence_holds_on_every_road(self):
        # single-topic resolve
        self.assertIsNone(visible_topic(self.sara, self.delta, str(self.configure.id)))
        self.assertIsNotNone(visible_topic(self.owner, self.delta, str(self.configure.id)))
        # the bulk ids helper (search, the gateway)
        self.assertNotIn(str(self.configure.id), visible_topic_ids(self.sara, self.company))
        self.assertIn(str(self.configure.id), visible_topic_ids(self.owner, self.company))
        # the messages API — invisible answers like nonexistent
        path = (f"/api/v1/projects/{self.delta.id}/channels/{self.general.id}"
                f"/topics/{self.configure.id}/messages/")
        self.assertEqual(self.call("get", path, self.sara).status_code, 404)
        self.assertEqual(self.call("get", path, self.owner).status_code, 200)

    def test_a_direct_topic_invite_does_not_pierce_the_fence(self):
        PermissionChecker.assign_role(self.sara, self.member_role, self.configure, granted_by=self.owner)
        self.assertIsNone(visible_topic(self.sara, self.delta, str(self.configure.id)))
        self.assertNotIn("configure", self.titles(self.sara))


ENGINE_TOOLS = [
    {"name": "search", "one_line": "Search code", "read_only": True},
    {"name": "create_issue", "one_line": "Open an issue", "read_only": None},
]
STORED = [
    {"name": "search", "description": "Search code", "read_only": True},
    {"name": "create_issue", "description": "Open an issue", "read_only": None},
]


class ToolListTests(MentionRightFixture):
    def server(self, **kw):
        defaults = dict(company=self.company, project=self.p1, name="GitHub",
                        server_type="hosted", transport="http", url="https://x.example/mcp")
        defaults.update(kw)
        return MCPServer.objects.create(**defaults)

    def refresh(self, user, server):
        return self.call("post", f"/api/v1/mcp-servers/{server.id}/tools/refresh/", user)

    def test_refresh_stores_the_list_and_gates_on_the_right(self):
        s = self.server()
        with patch("chat.nexus_ai.NexusAIClient.list_mcp_tools",
                   return_value=(True, ENGINE_TOOLS)) as dial:
            r = self.refresh(self.owner, s)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["tools"], STORED)
        dial.assert_called_once_with("https://x.example/mcp", None)
        s.refresh_from_db()
        self.assertEqual(s.tools, STORED)
        # a Member holds mcp_server.list, not .update — refused before any dial
        self.assertEqual(self.refresh(self.sara, s).status_code, 403)

    def test_a_failed_dial_answers_502_with_the_reason(self):
        s = self.server(name="Dead")
        with patch("chat.nexus_ai.NexusAIClient.list_mcp_tools",
                   return_value=(False, "could not list tools: ConnectError: boom")):
            r = self.refresh(self.owner, s)
        self.assertEqual(r.status_code, 502)
        self.assertIn("ConnectError", r.json()["detail"])
        s.refresh_from_db()
        self.assertEqual(s.tools, [])   # a failed dial never clobbers with junk

    def test_internal_and_non_http_rows_are_left_alone(self):
        internal = MCPServer.objects.create(
            company=self.company, project=self.p1, name="Caps",
            is_internal=True, auth_type="none",
            capability_config={"filesystem": {}},
        )
        with patch("chat.nexus_ai.NexusAIClient.list_mcp_tools") as dial:
            r = self.refresh(self.owner, internal)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["tools"], [])
        dial.assert_not_called()

    def test_the_engine_payload_carries_the_stored_list(self):
        from internal.api import _mcp_internal
        s = self.server(name="Shipped")
        s.tools = STORED
        s.save(update_fields=["tools"])
        out = _mcp_internal(s, needs_reauth=False)
        self.assertEqual(out.tools, STORED)


class PhoneHomeTests(MentionRightFixture):
    """Ruling 5: ONE value leaves — install token + total — and silence offline."""

    def test_one_total_leaves_with_the_install_token(self):
        from core import phone_home
        with self.settings(NEURALOPS_INSTALL_TOKEN="inst-1",
                           NEURALOPS_PHONE_HOME_URL="https://fn.example/phone-home"), \
             patch("core.phone_home.httpx.post") as post:
            post.return_value.status_code = 200
            self.assertTrue(phone_home.send("open"))
        self.assertEqual(post.call_args.kwargs["json"],
                         {"install_token": "inst-1", "event": "open", "total_tokens": 0})

    def test_nothing_sent_without_a_token_and_failure_is_silent(self):
        from core import phone_home
        with self.settings(NEURALOPS_INSTALL_TOKEN=""), \
             patch("core.phone_home.httpx.post") as post:
            self.assertFalse(phone_home.send("open"))
        post.assert_not_called()
        with self.settings(NEURALOPS_INSTALL_TOKEN="inst-1"), \
             patch("core.phone_home.httpx.post", side_effect=OSError("offline")):
            self.assertFalse(phone_home.send("close"))  # not raising IS the test
