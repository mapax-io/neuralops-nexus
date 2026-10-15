"""
Step 6 (docs/NUCLEUS-REVAMP.md) — the MCP gateway + its personal tokens.

The four-roles minting rule, the hashed token opening the MCP door AS its
person, the internal road (key + user header), the off switch, and the five
tools running with real visibility and rights — nothing on this road ever
acts as a master user.
"""
import json
from unittest.mock import AsyncMock, patch

from asgiref.sync import sync_to_async
from django.test import Client

from authn.permissions.checker import PermissionChecker
from authn.permissions.models import Role
from chat.tests import MentionRightFixture
from nucleus.models import ChatMessage, CompanyAccess, GatewayToken, User


class GatewayFixture(MentionRightFixture):
    def mint(self, as_user, name="laptop", user_id=None):
        body = {"name": name}
        if user_id:
            body["user_id"] = user_id
        return self.call("post", "/api/v1/gateway/tokens/", as_user, body)

    def token_for(self, user) -> str:
        r = self.mint(self.owner, name=f"for-{user.username}", user_id=str(user.id))
        assert r.status_code == 200, r.content
        return r.json()["token"]

    def mcp(self, token, method, params=None, rpc_id=1, **extra):
        body = {"jsonrpc": "2.0", "id": rpc_id, "method": method}
        if params is not None:
            body["params"] = params
        headers = {"HTTP_AUTHORIZATION": f"Bearer {token}"} if token else {}
        headers.update(extra)
        return Client().post("/api/v1/mcp/", data=json.dumps(body),
                             content_type="application/json", **headers)

    def tool(self, token, name, arguments=None, **extra):
        r = self.mcp(token, "tools/call", {"name": name, "arguments": arguments or {}}, **extra)
        assert r.status_code == 200, r.content
        result = r.json()["result"]
        text = result["content"][0]["text"]
        return result["isError"], (text if result["isError"] else json.loads(text))


class TokenMintingTests(GatewayFixture):
    """Ruling 2: four roles mint; a token never outruns its person."""

    def test_minting_follows_the_four_roles(self):
        r = self.mint(self.owner)                      # company owner
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(r.json()["token"].startswith("nxg_"))
        self.assertEqual(self.mint(self.sara).status_code, 403)   # Member
        self.assertEqual(self.mint(self.vera).status_code, 403)   # Viewer

        # A PROJECT-level admin reaches the right through their project…
        pat = User.objects.create_user(username="pat", email="pat@acme.test", password="x")
        CompanyAccess.objects.create(company=self.company, user=pat, role="member", invited_by=self.owner)
        PermissionChecker.assign_role(
            pat, Role.objects.get(company=self.company, name="Admin"), self.p1, granted_by=self.owner)
        r = self.mint(pat)
        self.assertEqual(r.status_code, 200, r.content)
        # …but only a COMPANY-level holder mints for someone else.
        r = self.mint(pat, user_id=str(self.vera.id))
        self.assertEqual(r.status_code, 403)
        r = self.mint(self.owner, user_id=str(self.sara.id))
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["user_email"], self.sara.email)

    def test_admins_see_every_token_members_see_their_own(self):
        self.mint(self.owner, name="mine")
        self.token_for(self.sara)
        r = self.call("get", "/api/v1/gateway/tokens/", self.sara)
        self.assertEqual([t["user_email"] for t in r.json()], [self.sara.email])
        r = self.call("get", "/api/v1/gateway/tokens/", self.owner)
        self.assertEqual(len(r.json()), 2)
        # sara revokes her own; she can't touch the owner's.
        sara_token_id = next(t["id"] for t in r.json() if t["user_email"] == self.sara.email)
        owner_token_id = next(t["id"] for t in r.json() if t["user_email"] == self.owner.email)
        self.assertEqual(self.call("delete", f"/api/v1/gateway/tokens/{owner_token_id}/", self.sara).status_code, 403)
        self.assertEqual(self.call("delete", f"/api/v1/gateway/tokens/{sara_token_id}/", self.sara).status_code, 200)


class McpDoorTests(GatewayFixture):
    """The wire shape and the three ways in (token, internal road, no way)."""

    def test_a_token_opens_the_door_as_its_person(self):
        token = self.token_for(self.sara)
        r = self.mcp(token, "initialize", {"protocolVersion": "2025-06-18"})
        self.assertEqual(r.status_code, 200, r.content)
        result = r.json()["result"]
        self.assertEqual(result["serverInfo"]["name"], "NeuralOps")
        self.assertEqual(result["protocolVersion"], "2025-06-18")
        r = self.mcp(token, "tools/list")
        names = [t["name"] for t in r.json()["result"]["tools"]]
        self.assertEqual(sorted(names), ["ask_persona", "list_projects", "list_topics",
                                         "post_message", "search_memory"])
        is_error, projects = self.tool(token, "list_projects")
        self.assertFalse(is_error, projects)
        self.assertIn("Alpha", [p["name"] for p in projects])

    def test_wrong_revoked_and_absent_tokens_are_401(self):
        self.assertEqual(self.mcp("nxg_not-a-token", "ping").status_code, 401)
        self.assertEqual(self.mcp(None, "ping").status_code, 401)
        token = self.token_for(self.sara)
        row = GatewayToken.objects.get(user=self.sara)
        self.call("delete", f"/api/v1/gateway/tokens/{row.id}/", self.owner)
        self.assertEqual(self.mcp(token, "ping").status_code, 401)

    def test_the_internal_road_needs_the_key_and_a_real_person(self):
        with self.settings(INTERNAL_API_KEY="ik-test"):
            ok = dict(HTTP_X_INTERNAL_KEY="ik-test", HTTP_X_NEURALOPS_USER=str(self.sara.id))
            is_error, projects = self.tool(None, "list_projects", **ok)
            self.assertFalse(is_error, projects)
            r = self.mcp(None, "ping", HTTP_X_INTERNAL_KEY="wrong",
                         HTTP_X_NEURALOPS_USER=str(self.sara.id))
            self.assertEqual(r.status_code, 401)
            r = self.mcp(None, "ping", HTTP_X_INTERNAL_KEY="ik-test")  # no person named
            self.assertEqual(r.status_code, 401)

    def test_the_off_switch_closes_the_whole_door(self):
        token = self.token_for(self.owner)
        with self.settings(GATEWAY_ENABLED=False):
            self.assertEqual(self.mcp(token, "initialize").status_code, 403)

    def test_notifications_and_unknown_methods(self):
        token = self.token_for(self.owner)
        r = Client().post("/api/v1/mcp/", data=json.dumps(
            {"jsonrpc": "2.0", "method": "notifications/initialized"}),
            content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {token}")
        self.assertEqual(r.status_code, 202)
        r = self.mcp(token, "resources/list")
        self.assertEqual(r.json()["error"]["code"], -32601)


class GatewayToolTests(GatewayFixture):
    """The five tools run on the app's own roads — visibility and rights hold."""

    def test_post_message_lands_in_the_topic(self):
        token = self.token_for(self.owner)
        with patch("chat.services.publish_async", new_callable=AsyncMock):
            is_error, out = self.tool(token, "post_message",
                                      {"topic_id": str(self.t1.id), "content": "hello from outside"})
        self.assertFalse(is_error, out)
        self.assertTrue(ChatMessage.objects.filter(id=out["message_id"], sender=self.owner,
                                                   content="hello from outside").exists())
        is_error, text = self.tool(token, "post_message",
                                   {"topic_id": "not-a-topic", "content": "x"})
        self.assertTrue(is_error)
        self.assertIn("No such topic", text)

    def test_list_topics_respects_the_project_wall(self):
        token = self.token_for(self.owner)
        is_error, topics = self.tool(token, "list_topics", {"project_id": str(self.p1.id)})
        self.assertFalse(is_error, topics)
        self.assertIn("t1", [t["title"] for t in topics])

    def test_ask_persona_returns_the_reply_content(self):
        token = self.token_for(self.sara)

        async def fake_run(**kwargs):
            def make():
                from django.db.models import Max
                topic = kwargs["topic"]
                seq = (ChatMessage.objects.filter(topic_id=topic.id)
                       .aggregate(Max("sequence"))["sequence__max"] or 0) + 1
                persona = kwargs["persona"]
                return ChatMessage.objects.create(
                    company=kwargs["company"], project=kwargs["project"], topic=topic,
                    sender=persona.identity_user, content="42 is the answer",
                    message_type=ChatMessage.MessageType.TEXT,
                    status=ChatMessage.Status.COMPLETED, sequence=seq,
                    metadata={"role": "assistant", "persona_id": str(persona.id),
                              "persona_name": persona.name},
                )
            await sync_to_async(make)()

        with patch("chat.services.trigger_ai_response_async", side_effect=fake_run), \
             patch("chat.services.publish_async", new_callable=AsyncMock):
            is_error, out = self.tool(token, "ask_persona",
                                      {"topic_id": str(self.t1.id), "persona": "Sara",
                                       "message": "what is the answer?"})
        self.assertFalse(is_error, out)
        self.assertEqual(out["status"], "completed")
        self.assertEqual(out["content"], "42 is the answer")
        # The road saved the asking message too, as the person.
        self.assertTrue(ChatMessage.objects.filter(
            topic=self.t1, sender=self.sara, content__icontains="what is the answer").exists())

    def test_ask_persona_keeps_the_rights_fence(self):
        token = self.token_for(self.vera)  # Viewer — no persona.mention
        with patch("chat.services.trigger_ai_response_async", new_callable=AsyncMock) as run, \
             patch("chat.services.publish_async", new_callable=AsyncMock):
            is_error, text = self.tool(token, "ask_persona",
                                       {"topic_id": str(self.t1.id), "persona": "Sara",
                                        "message": "hi"})
        self.assertTrue(is_error)
        self.assertIn("can't call personas", text)
        run.assert_not_called()

    def test_search_memory_filters_by_what_the_person_sees(self):
        from chat import services as chat_svc
        token = self.token_for(self.owner)
        msg = chat_svc.save_user_message(company=self.company, project=self.p1,
                                         topic=self.t1, user=self.sara,
                                         content="we picked pgbouncer")
        ghost = "00000000-0000-0000-0000-000000000000"
        with patch("chat.search.semantic_ids", new_callable=AsyncMock,
                   return_value=[msg["id"], ghost]):
            is_error, hits = self.tool(token, "search_memory", {"query": "pgbouncer"})
        self.assertFalse(is_error, hits)
        self.assertEqual([h["message_id"] for h in hits], [msg["id"]])
        self.assertIn("pgbouncer", hits[0]["preview"])
