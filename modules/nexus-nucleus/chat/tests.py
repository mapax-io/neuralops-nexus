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
