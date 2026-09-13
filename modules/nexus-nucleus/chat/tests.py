"""
Unit tests for the realtime event contract (chat/events.py).

Pure payload construction -- no DB, no HTTP. The relay in services.py decides
when to publish; these pin what it publishes.
"""
from django.test import SimpleTestCase

from chat.events import TOOL_ACTIVITY_LABELS, tool_activity_event


def call(name):
    """A worker tool_call_start event carrying `name`."""
    return {"type": "tool_call_start", "tool_call": {"name": name, "args": {}}}


class ToolActivityEventTests(SimpleTestCase):
    def test_built_in_tools_get_their_own_wording(self):
        event = tool_activity_event("m1", call("web_search"))
        self.assertEqual(event, {
            "type": "tool_activity",
            "id": "m1",
            "tool": "web_search",
            "label": "Searching the web",
        })

    def test_every_labelled_tool_round_trips(self):
        for name, label in TOOL_ACTIVITY_LABELS.items():
            with self.subTest(tool=name):
                self.assertEqual(tool_activity_event("m1", call(name))["label"], label)

    def test_an_unknown_tool_falls_back_to_its_name(self):
        # An MCP server's own tool -- must still read as a sentence.
        event = tool_activity_event("m1", call("search_warehouse"))
        self.assertEqual(event["label"], "Using search warehouse")
        self.assertEqual(event["tool"], "search_warehouse")

    def test_the_message_id_is_carried_through(self):
        # The swarm path passes the ACTIVE message id, not the first one.
        self.assertEqual(tool_activity_event("m9", call("shell"))["id"], "m9")

    def test_nothing_is_published_without_a_tool_name(self):
        # Publishing an empty cue would be worse than staying quiet.
        self.assertIsNone(tool_activity_event("m1", call("")))
        self.assertIsNone(tool_activity_event("m1", call("   ")))
        self.assertIsNone(tool_activity_event("m1", {"type": "tool_call_start"}))
        self.assertIsNone(tool_activity_event("m1", {"type": "tool_call_start", "tool_call": None}))

    def test_a_surrounding_whitespace_name_is_trimmed(self):
        self.assertEqual(tool_activity_event("m1", call("  shell  "))["tool"], "shell")

    def test_the_payload_type_is_what_the_web_app_parses(self):
        # lib/realtime/events.ts switches on this string; a rename here is a
        # silent break there.
        self.assertEqual(tool_activity_event("m1", call("shell"))["type"], "tool_activity")

    def test_label_is_always_present_and_non_empty(self):
        # The client renders label verbatim, so an empty one would show a blank cue.
        for name in ("web_search", "filesystem", "some_unmapped_tool"):
            with self.subTest(tool=name):
                self.assertTrue(tool_activity_event("m1", call(name))["label"].strip())


# ── persona.mention on the send path ─────────────────────────────────────────

from unittest.mock import AsyncMock, patch  # noqa: E402

from django.contrib.auth import get_user_model  # noqa: E402
from django.test import Client  # noqa: E402

from authn.permissions.checker import PermissionChecker  # noqa: E402
from authn.permissions.models import Role, RoleAssignment  # noqa: E402
from nucleus.models import ChatMessage, CompanyAccess, ModelConfig, Persona  # noqa: E402
from workspace.tests import InviteGrantsFixture  # noqa: E402

User = get_user_model()


class MentionRightFixture(InviteGrantsFixture):
    """
    The invite fixture plus two personas in Alpha (Sara, Bob) and Vera, a
    company-wide Viewer -- the one default role without persona.mention.
    """

    def setUp(self):
        super().setUp()
        self.model_config = ModelConfig.objects.create(
            company=self.company, name="GPT Test", provider="openai", model_id="gpt-test", supports_tools=True,
        )
        self.model_config.projects.add(self.p1)
        self.persona_sara = self.persona("Sara")
        self.persona_bob = self.persona("Bob")
        self.vera = User.objects.create_user(username="vera", email="vera@acme.test", password="x")
        CompanyAccess.objects.create(company=self.company, user=self.vera, role="viewer", invited_by=self.owner)
        self.assign(self.vera, "Viewer")

    def persona(self, name: str):
        shadow = User.objects.create(username=f"persona_{name.lower()}", user_type="persona", is_active=True)
        return Persona.objects.create(company=self.company, project=self.p1, identity_user=shadow, name=name, model=self.model_config)

    def assign(self, user, role_name: str):
        PermissionChecker.assign_role(user, Role.objects.get(company=self.company, name=role_name), self.company, granted_by=self.owner)

    def demote_to_viewer(self, user):
        RoleAssignment.objects.filter(user=user).delete()
        self.assign(user, "Viewer")

    def send(self, user, content: str):
        """POST a message as `user` with every fire-and-forget side effect mocked; returns (response, trigger, swarm, publish)."""
        path = f"/api/v1/projects/{self.p1.id}/channels/{self.c1.id}/topics/{self.t1.id}/messages/"
        with patch("authn.auth.verify_supabase_token", return_value={"email": user.email}), \
             patch("chat.api.chat_svc.trigger_ai_response_async", new_callable=AsyncMock) as trigger, \
             patch("chat.api.chat_svc.trigger_ai_swarm_response_async", new_callable=AsyncMock) as swarm, \
             patch("chat.api.chat_svc.publish_async", new_callable=AsyncMock) as publish, \
             patch("chat.api.chat_svc.embed_message_async", new_callable=AsyncMock):
            r = Client().post(path, data={"content": content}, content_type="application/json", HTTP_AUTHORIZATION="Bearer t")
        return r, trigger, swarm, publish

    @staticmethod
    def refused_events(publish) -> list:
        return [c.args[1] for c in publish.call_args_list if isinstance(c.args[1], dict) and c.args[1].get("type") == "mention_refused"]


class MentionRightTests(MentionRightFixture):
    """The right exists and the app hides the picker on it; the server must refuse too."""

    def test_a_member_mention_triggers_and_reports_no_refusal(self):
        r, trigger, swarm, publish = self.send(self.sara, "@Sara hello")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["refusals"], [])
        self.assertEqual(trigger.call_count, 1)
        self.assertEqual(trigger.call_args.kwargs["persona"].id, self.persona_sara.id)
        self.assertEqual(self.refused_events(publish), [])

    def test_a_viewer_mention_posts_the_message_but_never_triggers(self):
        r, trigger, swarm, publish = self.send(self.vera, "@Sara hello")
        self.assertEqual(r.status_code, 200, r.content)
        body = r.json()
        self.assertEqual(body["refusals"], [{
            "persona_id": str(self.persona_sara.id), "name": "Sara", "code": "no_right",
            "message": "You can't call personas in this topic.", "resets_at": None,
        }])
        self.assertTrue(ChatMessage.objects.filter(id=body["message"]["id"], sender=self.vera).exists())
        trigger.assert_not_called()
        swarm.assert_not_called()
        events = self.refused_events(publish)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["id"], body["message"]["id"])
        self.assertEqual(events[0]["actor_user_id"], str(self.vera.id))
        self.assertEqual(events[0]["refusals"], body["refusals"])

    def test_a_viewer_cannot_open_a_session_by_mentioning(self):
        r, trigger, swarm, publish = self.send(self.vera, "@Sara @session let's talk")
        self.assertEqual([x["name"] for x in r.json()["refusals"]], ["Sara"])
        trigger.assert_not_called()
        self.assertFalse(ChatMessage.objects.filter(topic=self.t1, message_type="system", content__icontains="Session with").exists())

    def test_a_viewer_swarm_never_starts(self):
        r, trigger, swarm, publish = self.send(self.vera, "@Sara @Bob compare notes /swarm")
        self.assertEqual(sorted(x["name"] for x in r.json()["refusals"]), ["Bob", "Sara"])
        swarm.assert_not_called()
        trigger.assert_not_called()

    def test_a_member_swarm_still_starts(self):
        r, trigger, swarm, publish = self.send(self.sara, "@Sara @Bob compare notes /swarm")
        self.assertEqual(r.json()["refusals"], [])
        self.assertEqual(swarm.call_count, 1)

    def test_a_session_auto_trigger_is_refused_once_the_right_is_gone(self):
        r, trigger, _, _ = self.send(self.sara, "@Sara @session hi there")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(trigger.call_count, 1)
        self.demote_to_viewer(self.sara)
        r, trigger, _, publish = self.send(self.sara, "and another thing")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual([x["name"] for x in r.json()["refusals"]], ["Sara"])
        trigger.assert_not_called()
        self.assertEqual(len(self.refused_events(publish)), 1)

    def test_a_plain_message_carries_no_refusals(self):
        r, trigger, _, publish = self.send(self.vera, "just reading along")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["refusals"], [])
        trigger.assert_not_called()
        self.assertEqual(self.refused_events(publish), [])
