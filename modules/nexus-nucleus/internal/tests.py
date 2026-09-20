"""
The internal API nexus-ai calls back into. Only what the worker reads off it
is pinned here; the filtering itself is the worker's (nucleus_client.py).
"""
import os
from unittest.mock import patch

from django.test import Client

from chat.tests import MentionRightFixture
from nucleus.models import ChatMessage


class TopicHistoryInternalTests(MentionRightFixture):
    def history(self):
        with patch.dict(os.environ, {"INTERNAL_API_KEY": "k"}):
            r = Client().get(f"/api/v1/internal/topics/{self.t1.id}/history/", HTTP_X_INTERNAL_API_KEY="k")
        self.assertEqual(r.status_code, 200)
        return r.json()

    def reply(self, content, **metadata):
        return ChatMessage.objects.create(
            company=self.company, project=self.p1, topic=self.t1, sender=self.persona_sara.identity_user,
            content=content, sequence=ChatMessage.objects.filter(topic=self.t1).count() + 1,
            metadata={"persona_id": str(self.persona_sara.id), "persona_name": "Sara", **metadata},
        )

    def test_a_stopped_reply_is_marked_so_the_worker_can_leave_it_out(self):
        self.reply("full answer", render_as="chart", output_type="chart")
        self.reply('{"type": "bar", "ti', render_as="text", output_type="text", stopped=True)
        rows = self.history()
        self.assertEqual([(r["content"], r["stopped"], r["render_as"]) for r in rows], [
            ("full answer", False, "chart"),
            ('{"type": "bar", "ti', True, "text"),
        ])

    def test_the_wrong_key_is_refused(self):
        with patch.dict(os.environ, {"INTERNAL_API_KEY": "k"}):
            r = Client().get(f"/api/v1/internal/topics/{self.t1.id}/history/", HTTP_X_INTERNAL_API_KEY="nope")
        self.assertEqual(r.status_code, 401)
