"""
scheduling/tests.py

A schedule is a standing @mention: creating one needs the right to call
personas in the topic, and every fire re-checks its creator.
"""
from unittest.mock import AsyncMock, patch

from django.test import Client

from authn.permissions.models import Right, Role, RoleRight
from chat.tests import MentionRightFixture
from nucleus.models import ChatMessage, CompanyAccess, PersonaSchedule
from scheduling.tasks import fire_persona_schedule


class ScheduleMentionRightTests(MentionRightFixture):

    def create(self, user, persona=None):
        path = f"/api/v1/projects/{self.p1.id}/channels/{self.c1.id}/topics/{self.t1.id}/schedules/"
        body = {
            "persona_id": str((persona or self.persona_sara).id), "query_text": "daily summary",
            "schedule_kind": "interval", "interval_every": 1, "interval_period": "days",
        }
        with patch("authn.auth.verify_supabase_token", return_value={"email": user.email}), \
             patch("scheduling.api.chat_svc.publish"):
            return Client().post(path, data=body, content_type="application/json", HTTP_AUTHORIZATION="Bearer t")

    def fire(self, schedule_id):
        with patch("chat.services.trigger_ai_response_async", new_callable=AsyncMock) as trigger, \
             patch("chat.services.publish") as publish:
            fire_persona_schedule(str(schedule_id))
        return trigger, publish

    def test_creating_a_schedule_needs_the_mention_right_not_just_schedule_create(self):
        # A custom role that may schedule and see the topic but may not call personas.
        scheduler = Role.objects.create(company=self.company, name="Scheduler")
        for code in ("project.list", "project.view", "channel.list", "topic.list", "schedule.create"):
            RoleRight.objects.create(role=scheduler, right=Right.objects.get(code=code))
        self.assign(self.vera, "Scheduler")
        r = self.create(self.vera)
        self.assertEqual(r.status_code, 403, r.content)
        self.assertIn("call personas", r.json()["detail"])
        self.assertFalse(PersonaSchedule.objects.exists())
        r = self.create(self.sara)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(PersonaSchedule.objects.get().created_by, self.sara)

    def test_a_fire_re_checks_its_creator_and_announces_a_skip(self):
        self.assertEqual(self.create(self.sara).status_code, 200)
        schedule = PersonaSchedule.objects.get()
        trigger, _ = self.fire(schedule.id)
        self.assertEqual(trigger.call_count, 1)
        self.assertEqual(trigger.call_args.kwargs["persona"].id, self.persona_sara.id)

        self.demote_to_viewer(self.sara)
        trigger, publish = self.fire(schedule.id)
        trigger.assert_not_called()
        schedule.refresh_from_db()
        self.assertEqual(schedule.last_status, PersonaSchedule.RunStatus.FAILED)
        self.assertIn("can no longer call personas", schedule.last_error)
        skipped = ChatMessage.objects.filter(topic=self.t1, message_type="system", content__startswith="Scheduled run of @Sara skipped")
        self.assertEqual(skipped.count(), 1)
        self.assertEqual(publish.call_count, 1)  # the skip notice, nothing else

    def test_a_fire_belongs_to_the_schedule_s_creator(self):
        """W22: the creator is the caller — the only one who may stop the scheduled reply."""
        self.assertEqual(self.create(self.sara).status_code, 200)
        trigger, _ = self.fire(PersonaSchedule.objects.get().id)
        self.assertEqual(trigger.call_args.kwargs["triggered_by"], self.sara)

    def test_a_fire_whose_creator_is_gone_is_skipped(self):
        self.assertEqual(self.create(self.sara).status_code, 200)
        schedule = PersonaSchedule.objects.get()
        PersonaSchedule.objects.filter(id=schedule.id).update(created_by=None)
        trigger, _ = self.fire(schedule.id)
        trigger.assert_not_called()
        schedule.refresh_from_db()
        self.assertEqual(schedule.last_status, PersonaSchedule.RunStatus.FAILED)
        self.assertIn("creator", schedule.last_error)
