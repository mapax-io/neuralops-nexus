"""
scheduling/tests.py

A schedule is a standing @mention: creating one needs the right to call
personas in the topic, and every fire re-checks its creator.
"""
import uuid
from unittest.mock import AsyncMock, patch

from django.test import Client

from authn.permissions.models import Right, Role, RoleAssignment, RoleRight
from chat.tests import MentionRightFixture
from nucleus.models import ChatMessage, CompanyAccess, PersonaSchedule, User
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


# ── Runbooks (W6) ─────────────────────────────────────────────────────────────

from asgiref.sync import sync_to_async  # noqa: E402

from nucleus.models import Runbook, RunbookRun  # noqa: E402
from scheduling import runbooks  # noqa: E402
from scheduling.runbooks import execute_run  # noqa: E402


class RunbookFixture(MentionRightFixture):
    """A runbook of three steps in Alpha, and a fake worker: each trigger writes a reply row as scripted."""

    def setUp(self):
        super().setUp()
        self.runs_path = f"/api/v1/projects/{self.p1.id}/runbooks/"
        self.steps = [
            {"persona_id": str(self.persona_sara.id), "prompt": "Gather the numbers."},
            {"persona_id": str(self.persona_bob.id), "prompt": "Check them.", "on_failure": "skip"},
            {"persona_id": str(self.persona_sara.id), "prompt": "Write the summary.", "output_type": "chart"},
        ]

    def create(self, user=None, **over):
        body = {"title": "Weekly ops update", "description": "Numbers, check, summary.", "steps": self.steps, **over}
        return self.call("post", self.runs_path, user or self.owner, body)

    def runbook(self) -> Runbook:
        r = self.create()
        self.assertEqual(r.status_code, 200, r.content)
        return Runbook.objects.get(id=r.json()["id"])

    def start(self, runbook, user=None, body=None):
        with patch("scheduling.tasks.run_runbook.delay") as delay:
            r = self.call("post", f"{self.runs_path}{runbook.id}/run/", user or self.sara, body or {"topic_id": str(self.t1.id)})
        return r, delay

    def execute(self, run_id, script):
        """
        Run the loop with the worker faked: `script` maps a 1-based step to what its
        reply becomes -- "done" (content "reply <n>"), "failed", "stopped" -- or a
        list of outcomes for successive attempts. Returns the trigger's kwargs per call.
        """
        from chat.services import create_ai_message
        calls: list[dict] = []
        attempts: dict[int, int] = {}

        def reply(kw, outcome):
            step = kw["runbook_run"]["step"]
            msg = create_ai_message(kw["company"], kw["project"], kw["topic"], kw["persona"], triggered_by=kw.get("triggered_by"), runbook_run=kw["runbook_run"])
            row = ChatMessage.objects.get(id=msg["id"])
            fields = {"done": dict(status="completed", content=f"reply {step}"),
                      "failed": dict(status="failed", content="The model provider refused the key."),
                      "stopped": dict(status="completed", content="partial", metadata={**row.metadata, "stopped": True})}[outcome]
            ChatMessage.objects.filter(id=msg["id"]).update(**fields)
            return msg["id"]

        async def fake_trigger(**kw):
            calls.append(kw)
            step = kw["runbook_run"]["step"]
            attempts[step] = attempts.get(step, 0) + 1
            planned = script.get(step, "done")
            outcome = planned[min(attempts[step], len(planned)) - 1] if isinstance(planned, list) else planned
            return await sync_to_async(reply)(kw, outcome)

        with patch("chat.services.trigger_ai_response_async", new=AsyncMock(side_effect=fake_trigger)), \
             patch("chat.services.publish"), patch("chat.services.publish_async", new_callable=AsyncMock):
            execute_run(str(run_id))
        return calls

    def lines(self, topic=None):
        return list(ChatMessage.objects.filter(topic=topic or self.t1, message_type="system").order_by("sequence").values_list("content", flat=True))


class RunbookApiTests(RunbookFixture):

    def test_create_needs_runbook_manage_and_validates_the_steps(self):
        self.assertEqual(self.create(self.sara).status_code, 403)  # a member runs runbooks, admins define them
        self.assertEqual(self.create(steps=[]).status_code, 400)
        self.assertIn("1 to 12", self.create(steps=[]).json()["detail"])
        other = {"persona_id": str(uuid.uuid4()), "prompt": "x"}
        self.assertIn("persona", self.create(steps=[other]).json()["detail"])
        self.assertIn("prompt", self.create(steps=[{"persona_id": str(self.persona_sara.id), "prompt": " "}]).json()["detail"])
        self.assertIn("on_failure", self.create(steps=[{**self.steps[0], "on_failure": "explode"}]).json()["detail"])
        self.assertIn("routine", self.create(steps=[{**self.steps[0], "routine_id": str(uuid.uuid4())}]).json()["detail"])
        r = self.create()
        self.assertEqual(r.status_code, 200, r.content)
        out = r.json()
        self.assertEqual(out["title"], "Weekly ops update")
        self.assertEqual([s["persona_name"] for s in out["steps"]], ["Sara", "Bob", "Sara"])
        self.assertEqual([s["on_failure"] for s in out["steps"]], ["stop", "skip", "stop"])
        self.assertEqual([s["output_type"] for s in out["steps"]], ["auto", "auto", "chart"])
        self.assertEqual(out["created_by_id"], str(self.owner.id))
        # Whoever reads the project sees the list -- Vera is a company Viewer.
        r = self.call("get", self.runs_path, self.vera)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual([x["title"] for x in r.json()], ["Weekly ops update"])

    def test_patch_and_delete_keep_the_run_history(self):
        rb = self.runbook()
        r = self.call("patch", f"{self.runs_path}{rb.id}/", self.owner, {"title": "Weekly update", "steps": self.steps[:1]})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual((r.json()["title"], len(r.json()["steps"])), ("Weekly update", 1))
        self.assertEqual(self.call("patch", f"{self.runs_path}{rb.id}/", self.owner, {"steps": []}).status_code, 400)
        self.assertEqual(self.call("patch", f"{self.runs_path}{rb.id}/", self.sara, {"title": "x"}).status_code, 403)
        run = RunbookRun.objects.create(company=self.company, project=self.p1, runbook=rb, topic=self.t1, started_by=self.sara, status="done")
        self.assertEqual(self.call("delete", f"{self.runs_path}{rb.id}/", self.owner).status_code, 204)
        self.assertEqual(self.call("get", self.runs_path, self.owner).json(), [])
        run.refresh_from_db()
        self.assertEqual(run.runbook_id, rb.id)  # history stays

    def test_run_now_needs_runbook_run_and_the_mention_right_and_queues_the_task(self):
        rb = self.runbook()
        r, delay = self.start(rb, self.vera)
        self.assertEqual(r.status_code, 403, r.content)
        delay.assert_not_called()
        # A member with runbook.run but no persona.mention here may not start it either.
        r, delay = self.start(rb, self.sara)
        self.assertEqual(r.status_code, 200, r.content)
        run = RunbookRun.objects.get()
        self.assertEqual((run.status, run.started_by, run.topic_id, run.current_step), ("queued", self.sara, self.t1.id, -1))
        delay.assert_called_once_with(str(run.id))
        self.assertEqual(r.json()["status"], "queued")
        self.assertEqual(r.json()["step_count"], 3)
        self.assertEqual(r.json()["started_by_name"], self.sara.get_display_name())

    def test_run_now_in_a_new_chat_creates_the_topic(self):
        rb = self.runbook()
        r, _ = self.start(rb, self.sara, {"channel_id": str(self.c1.id), "title": "Ops update, week 38"})
        self.assertEqual(r.status_code, 200, r.content)
        run = RunbookRun.objects.get()
        self.assertEqual(run.topic.title, "Ops update, week 38")
        self.assertEqual(run.topic.channel_id, self.c1.id)
        self.assertEqual(r.json()["topic_id"], str(run.topic_id))
        # Without a title the runbook's own name names the chat.
        r, _ = self.start(rb, self.sara, {"channel_id": str(self.c1.id)})
        self.assertEqual(RunbookRun.objects.get(id=r.json()["id"]).topic.title, "Weekly ops update")

    def test_runs_are_listed_by_runbook_topic_or_activity(self):
        rb = self.runbook()
        done = RunbookRun.objects.create(company=self.company, project=self.p1, runbook=rb, topic=self.t1, started_by=self.sara, status="done")
        running = RunbookRun.objects.create(company=self.company, project=self.p1, runbook=rb, topic=self.t2, started_by=self.sara, status="running")
        base = f"{self.runs_path}runs/"
        def ids(r):
            self.assertEqual(r.status_code, 200, r.content[:600])
            return [x["id"] for x in r.json()]
        self.assertEqual(set(ids(self.call("get", f"{base}?runbook_id={rb.id}", self.vera))), {str(done.id), str(running.id)})
        self.assertEqual(ids(self.call("get", f"{base}?topic_id={self.t2.id}", self.vera)), [str(running.id)])
        self.assertEqual(ids(self.call("get", f"{base}?active=1", self.vera)), [str(running.id)])
        self.assertEqual(ids(self.call("get", f"{base}?active=true", self.vera)), [str(running.id)])
        # "false" is false: bool("false") was True, so asking for every run gave
        # only the active ones (audit, 2026-09-21).
        self.assertEqual(set(ids(self.call("get", f"{base}?active=false", self.vera))), {str(done.id), str(running.id)})

    def test_stop_ends_a_queued_run_and_signals_a_running_reply(self):
        rb = self.runbook()
        r, _ = self.start(rb, self.sara)
        run = RunbookRun.objects.get(id=r.json()["id"])
        self.assertEqual(self.call("post", f"{self.runs_path}runs/{run.id}/stop/", self.vera).status_code, 403)
        with patch("scheduling.api.chat_svc.publish"):
            r = self.call("post", f"{self.runs_path}runs/{run.id}/stop/", self.sara)
        self.assertEqual(r.status_code, 200, r.content)
        run.refresh_from_db()
        self.assertEqual((run.status, run.error), ("stopped", f"Stopped by {self.sara.get_display_name()}"))
        self.assertIsNotNone(run.ended_at)
        self.assertEqual(self.lines(), ["Runbook: Weekly ops update stopped by " + self.sara.get_display_name() + " before it started."])
        self.assertEqual(self.call("post", f"{self.runs_path}runs/{run.id}/stop/", self.sara).status_code, 409)
        # A running run: the current reply gets the stop signal; the loop ends it.
        from chat.services import create_ai_message
        running = RunbookRun.objects.create(company=self.company, project=self.p1, runbook=rb, topic=self.t1, started_by=self.sara, status="running", current_step=1)
        reply = create_ai_message(self.company, self.p1, self.t1, self.persona_bob, runbook_run={"id": str(running.id), "title": rb.title, "step": 2, "of": 3})
        with patch("scheduling.api.chat_svc.publish"), patch("scheduling.runbooks.stop_signals") as signals:
            signals.return_value.request_stop = AsyncMock()
            r = self.call("post", f"{self.runs_path}runs/{running.id}/stop/", self.sara)
        self.assertEqual(r.status_code, 200, r.content)
        signals.return_value.request_stop.assert_awaited_once_with(reply["id"])
        running.refresh_from_db()
        self.assertEqual(running.status, "stopped")
        # Stamped here too: if the worker driving it is already gone, nothing
        # else ever would, and the banner read "stopped" with no end for good.
        self.assertIsNotNone(running.ended_at)


class RunbookExecutionTests(RunbookFixture):

    def test_steps_run_in_order_and_each_sees_the_previous_reply(self):
        rb = self.runbook()
        r, _ = self.start(rb, self.sara)
        run = RunbookRun.objects.get(id=r.json()["id"])
        calls = self.execute(run.id, {})
        self.assertEqual([c["persona"].name for c in calls], ["Sara", "Bob", "Sara"])
        self.assertEqual([c["user_message"] for c in calls], ["Gather the numbers.", "Check them.", "Write the summary."])
        self.assertEqual([c["step_context"] for c in calls], [None, "reply 1", "reply 2"])
        self.assertEqual([c["output_type"] for c in calls], ["auto", "auto", "chart"])
        self.assertEqual([(c["runbook_run"]["step"], c["runbook_run"]["of"]) for c in calls], [(1, 3), (2, 3), (3, 3)])
        self.assertTrue(all(c["triggered_by"] == self.sara and c["interactive"] is False for c in calls))
        run.refresh_from_db()
        self.assertEqual((run.status, run.current_step), ("done", 2))
        self.assertEqual([s["status"] for s in run.step_results], ["done", "done", "done"])
        self.assertEqual([s["persona_name"] for s in run.step_results], ["Sara", "Bob", "Sara"])
        self.assertTrue(all(s["message_id"] and s["started_at"] and s["ended_at"] for s in run.step_results))
        self.assertIsNotNone(run.ended_at)
        self.assertEqual(self.lines(), [
            f"Runbook: Weekly ops update started by {self.sara.get_display_name()} — 3 steps.",
            "Runbook: Weekly ops update finished — 3 steps.",
        ])
        self.assertEqual(runbooks.serialise_run(run)["skipped_count"], 0)
        # Every reply row says which step it was.
        rows = ChatMessage.objects.filter(topic=self.t1, metadata__has_key="runbook_run").order_by("sequence")
        self.assertEqual([m.metadata["runbook_run"]["step"] for m in rows], [1, 2, 3])
        from chat.services import _serialise
        self.assertEqual(_serialise(rows[0])["runbook_run"], {"id": str(run.id), "title": "Weekly ops update", "step": 1, "of": 3})

    def test_a_run_is_claimed_once_and_a_second_delivery_does_nothing(self):
        # Two deliveries of one task both read "queued" and both drove every step
        # into the chat; the transition is now a conditional update.
        rb = self.runbook()
        run = RunbookRun.objects.get(id=self.start(rb, self.sara)[0].json()["id"])
        calls = self.execute(run.id, {})
        self.assertEqual(len(calls), 3)
        again = self.execute(run.id, {})
        self.assertEqual(again, [])
        run.refresh_from_db()
        self.assertEqual(run.status, "done")
        self.assertEqual(len(run.step_results), 3)

    def test_a_run_the_server_stops_driving_ends_as_failed_not_running_for_ever(self):
        # Nothing reaps active runs and a lost task is not redelivered, so every
        # exit that is not an ending has to be made one.
        rb = self.runbook()
        run = RunbookRun.objects.get(id=self.start(rb, self.sara)[0].json()["id"])
        with patch("scheduling.runbooks._run_step", side_effect=RuntimeError("the database went away")), \
             patch("chat.services.publish"):
            with self.assertRaises(RuntimeError):
                runbooks.execute_run(str(run.id))
        run.refresh_from_db()
        self.assertEqual(run.status, "failed")
        self.assertIsNotNone(run.ended_at)
        self.assertIn("RuntimeError", run.error)
        self.assertEqual(self.lines()[-1], "Runbook: Weekly ops update stopped unexpectedly — the server could not carry it to the end.")

    def test_a_failed_step_follows_its_policy(self):
        rb = self.runbook()
        # skip: step 2 fails, step 3 still runs with step 1's output.
        run = RunbookRun.objects.get(id=self.start(rb, self.sara)[0].json()["id"])
        calls = self.execute(run.id, {2: "failed"})
        self.assertEqual(len(calls), 3)
        self.assertEqual(calls[2]["step_context"], "reply 1")
        run.refresh_from_db()
        self.assertEqual(run.status, "done")
        self.assertEqual([s["status"] for s in run.step_results], ["done", "skipped", "done"])
        self.assertIn("refused", run.step_results[1]["error"])
        # A skipped step is never hidden behind a plain "finished".
        self.assertEqual(runbooks.serialise_run(run)["skipped_count"], 1)
        self.assertEqual(self.lines()[-1], "Runbook: Weekly ops update finished — 3 steps, 1 skipped.")
        # stop (the default): step 1 fails, nothing else runs, the line says why.
        run = RunbookRun.objects.get(id=self.start(rb, self.sara)[0].json()["id"])
        calls = self.execute(run.id, {1: "failed"})
        self.assertEqual(len(calls), 1)
        run.refresh_from_db()
        self.assertEqual((run.status, run.current_step), ("failed", 0))
        self.assertEqual([s["status"] for s in run.step_results], ["failed"])
        self.assertEqual(runbooks.serialise_run(run)["skipped_count"], 0)  # failed, not skipped
        self.assertIn("step 1 of 3", run.error)
        self.assertEqual(self.lines()[-1], "Runbook: Weekly ops update failed at step 1 of 3 — The model provider refused the key.")
        # retry: one more attempt, then the step counts as failed under the stop rule.
        rb.steps[0]["on_failure"] = "retry"
        rb.save()
        run = RunbookRun.objects.get(id=self.start(rb, self.sara)[0].json()["id"])
        calls = self.execute(run.id, {1: ["failed", "done"]})
        self.assertEqual([c["runbook_run"]["step"] for c in calls], [1, 1, 2, 3])
        run.refresh_from_db()
        self.assertEqual(run.status, "done")
        self.assertEqual(run.step_results[0]["attempts"], 2)
        run = RunbookRun.objects.get(id=self.start(rb, self.sara)[0].json()["id"])
        calls = self.execute(run.id, {1: ["failed", "failed"]})
        self.assertEqual([c["runbook_run"]["step"] for c in calls], [1, 1])
        run.refresh_from_db()
        self.assertEqual(run.status, "failed")

    def test_a_stopped_reply_or_a_stopped_run_ends_the_runbook(self):
        rb = self.runbook()
        run = RunbookRun.objects.get(id=self.start(rb, self.sara)[0].json()["id"])
        calls = self.execute(run.id, {2: "stopped"})
        self.assertEqual(len(calls), 2)
        run.refresh_from_db()
        self.assertEqual((run.status, [s["status"] for s in run.step_results]), ("stopped", ["done", "stopped"]))
        self.assertEqual(self.lines()[-1], "Runbook: Weekly ops update stopped at step 2 of 3.")
        # A stopped step is not a skipped one -- the count means what it says.
        self.assertEqual(runbooks.serialise_run(run)["skipped_count"], 0)
        # Marked stopped from outside between steps: the loop does not start the next one.
        run = RunbookRun.objects.get(id=self.start(rb, self.sara)[0].json()["id"])
        original = execute_run.__globals__["_after_step"]

        def stop_after_first(run_obj, *a, **kw):
            RunbookRun.objects.filter(id=run_obj.id).update(status="stopped", error="Stopped by Sara")
            return original(run_obj, *a, **kw)

        with patch("scheduling.runbooks._after_step", side_effect=stop_after_first):
            calls = self.execute(run.id, {})
        self.assertEqual(len(calls), 1)
        run.refresh_from_db()
        self.assertEqual(run.status, "stopped")
        self.assertIsNotNone(run.ended_at)
        self.assertEqual(self.lines()[-1], "Runbook: Weekly ops update stopped by Sara after step 1 of 3.")

    def test_a_run_re_checks_its_starter_and_a_missing_persona_fails_the_step(self):
        rb = self.runbook()
        run = RunbookRun.objects.get(id=self.start(rb, self.sara)[0].json()["id"])
        self.demote_to_viewer(self.sara)
        calls = self.execute(run.id, {})
        self.assertEqual(calls, [])
        run.refresh_from_db()
        self.assertEqual(run.status, "failed")
        self.assertIn("can no longer call personas", run.error)
        self.assertEqual(self.lines()[-1], f"Runbook: Weekly ops update did not start — {self.sara.email} can no longer call personas in this chat.")
        # A persona removed after the runbook was written: that step fails (here under skip).
        self.assign(self.sara, "Member")
        run = RunbookRun.objects.get(id=self.start(rb, self.sara)[0].json()["id"])
        self.persona_bob.soft_delete()
        calls = self.execute(run.id, {})
        self.assertEqual([c["runbook_run"]["step"] for c in calls], [1, 3])
        run.refresh_from_db()
        self.assertEqual([s["status"] for s in run.step_results], ["done", "skipped", "done"])
        self.assertIn("persona", run.step_results[1]["error"])


class RunbookScheduleTests(RunbookFixture):

    def test_a_schedule_can_start_a_runbook_instead_of_a_persona(self):
        rb = self.runbook()
        path = f"/api/v1/projects/{self.p1.id}/channels/{self.c1.id}/topics/{self.t1.id}/schedules/"
        body = {"runbook_id": str(rb.id), "schedule_kind": "interval", "interval_every": 1, "interval_period": "days"}
        with patch("scheduling.api.chat_svc.publish"):
            self.assertEqual(self.call("post", path, self.vera, body).status_code, 403)
            r = self.call("post", path, self.sara, body)
        self.assertEqual(r.status_code, 200, r.content)
        out = r.json()
        self.assertEqual((out["persona_id"], out["persona_name"], out["runbook_id"], out["runbook_title"]), (None, "", str(rb.id), "Weekly ops update"))
        with patch("scheduling.api.chat_svc.publish"):
            both = self.call("post", path, self.sara, {**body, "persona_id": str(self.persona_sara.id)})
            neither = self.call("post", path, self.sara, {k: v for k, v in body.items() if k != "runbook_id"})
        self.assertEqual((both.status_code, neither.status_code), (400, 400))
        schedule = PersonaSchedule.objects.get()
        # Handed to its own task, not driven inside the beat-fired one: a long run
        # used to inherit this task's time limit and die mid-flight.
        with patch("chat.services.publish"), patch("scheduling.tasks.run_runbook.delay") as run_it:
            fire_persona_schedule(str(schedule.id))
        run = RunbookRun.objects.get()
        self.assertEqual((run.runbook_id, run.topic_id, run.started_by), (rb.id, self.t1.id, self.sara))
        run_it.assert_called_once_with(str(run.id))
        schedule.refresh_from_db()
        self.assertEqual(schedule.last_status, PersonaSchedule.RunStatus.SUCCESS)
        listed = self.call("get", path, self.sara).json()
        self.assertEqual(listed[0]["runbook_title"], "Weekly ops update")


# ── Inbound hooks (W12) ───────────────────────────────────────────────────────

import hashlib  # noqa: E402

from nucleus.models import InboundHook  # noqa: E402
from scheduling import hooks as hook_svc  # noqa: E402


class HookFixture(MentionRightFixture):
    """A hook into t1 calling Sara, created by sara, with the shared store swapped for a memory one."""

    def setUp(self):
        super().setUp()
        # hook.manage is Admin-tier in the registry (a hook lends a persona's
        # reach to a machine), so the fixture's creator holds Admin.
        self.assign(self.sara, "Admin")
        self.manage_path = f"/api/v1/projects/{self.p1.id}/channels/{self.c1.id}/topics/{self.t1.id}/hooks/"
        from chat.stop_signals import MemoryStore
        self.store = MemoryStore()
        patcher = patch("scheduling.hooks.signal_store", return_value=self.store)
        patcher.start()
        self.addCleanup(patcher.stop)

    def create(self, user=None, persona=None, label="Build monitor"):
        body = {"persona_id": str((persona or self.persona_sara).id), "label": label}
        return self.call("post", self.manage_path, user or self.sara, body)

    def hook_with_token(self):
        r = self.create()
        self.assertEqual(r.status_code, 200, r.content)
        return InboundHook.objects.get(id=r.json()["id"]), r.json()["token"]

    def fire(self, token, body=None, **kw):
        # _trigger_personas answers with the refusals (none here); a bare AsyncMock
        # would answer with a truthy MagicMock, which fire() would read as one.
        with patch("scheduling.hooks.chat_api._trigger_personas", new_callable=AsyncMock, return_value=[]) as trigger, \
             patch("chat.services.publish_async", new_callable=AsyncMock) as publish, \
             patch("chat.services.embed_message_async", new_callable=AsyncMock):
            r = Client().post(f"/api/v1/hooks/{token}/", data=body if body is not None else {"text": "the build is red"},
                              content_type="application/json", **kw)
        return r, trigger, publish


class HookManagementTests(HookFixture):

    def test_creating_needs_hook_manage_and_the_mention_right_and_shows_the_token_once(self):
        # A Viewer, and an ordinary Member, may not define hooks -- it is Admin-tier.
        self.assertEqual(self.create(self.vera).status_code, 403)
        member = User.objects.create_user(username="milo", email="milo@acme.test", password="x")
        CompanyAccess.objects.create(company=self.company, user=member, role="member", invited_by=self.owner)
        self.assign(member, "Member")
        self.assertEqual(self.create(member).status_code, 403)
        r = self.create()
        self.assertEqual(r.status_code, 200, r.content)
        out = r.json()
        token = out["token"]
        self.assertGreaterEqual(len(token), 32)
        hook = InboundHook.objects.get()
        self.assertEqual(hook.token_hash, hashlib.sha256(token.encode()).hexdigest())
        self.assertNotIn(token, hook.token_hash)
        self.assertEqual(hook.token_hint, token[-4:])
        self.assertEqual((hook.created_by, hook.persona_id, hook.topic_id), (self.sara, self.persona_sara.id, self.t1.id))
        self.assertEqual((out["persona_name"], out["label"], out["token_hint"], out["fire_count"]), ("Sara", "Build monitor", token[-4:], 0))
        # The list never carries the token again -- only the hint.
        listed = self.call("get", self.manage_path, self.sara).json()
        self.assertEqual(len(listed), 1)
        self.assertIsNone(listed[0].get("token"))  # never again, only the hint
        self.assertEqual(listed[0]["token_hint"], token[-4:])

    def test_a_member_who_cannot_call_personas_here_cannot_leave_a_hook_that_does(self):
        scheduler = Role.objects.create(company=self.company, name="Hooker")
        for code in ("project.list", "project.view", "channel.list", "topic.list", "hook.manage"):
            RoleRight.objects.create(role=scheduler, right=Right.objects.get(code=code))
        RoleAssignment.objects.filter(user=self.vera).delete()
        self.assign(self.vera, "Hooker")
        r = self.create(self.vera)
        self.assertEqual(r.status_code, 403, r.content)
        self.assertIn("call personas", r.json()["detail"])

    def test_pause_regenerate_and_remove(self):
        hook, token = self.hook_with_token()
        r = self.call("patch", f"{self.manage_path}{hook.id}/", self.sara, {"is_paused": True, "label": "Nightly build"})
        self.assertEqual(r.status_code, 200, r.content)
        hook.refresh_from_db()
        self.assertEqual((hook.is_paused, hook.label), (True, "Nightly build"))
        # Regenerate answers with a NEW token once, and the old one stops working.
        r = self.call("post", f"{self.manage_path}{hook.id}/regenerate/", self.sara)
        self.assertEqual(r.status_code, 200, r.content)
        fresh = r.json()["token"]
        self.assertNotEqual(fresh, token)
        hook.refresh_from_db()
        self.assertEqual(hook.token_hash, hashlib.sha256(fresh.encode()).hexdigest())
        self.assertEqual(self.fire(token)[0].status_code, 404)
        # Removing is a soft delete: the row goes, its topic keeps its messages.
        self.assertEqual(self.call("delete", f"{self.manage_path}{hook.id}/", self.sara).status_code, 204)
        self.assertEqual(self.call("get", self.manage_path, self.sara).json(), [])
        self.assertEqual(self.fire(fresh)[0].status_code, 404)

    def test_only_this_topic_s_hooks_are_listed_and_reachable(self):
        hook, _ = self.hook_with_token()
        other = f"/api/v1/projects/{self.p1.id}/channels/{self.c1.id}/topics/{self.t2.id}/hooks/"
        self.assertEqual(self.call("get", other, self.sara).json(), [])
        self.assertEqual(self.call("patch", f"{other}{hook.id}/", self.sara, {"is_paused": True}).status_code, 404)


class HookFireTests(HookFixture):

    def test_a_fire_posts_the_creator_s_message_and_triggers_the_persona(self):
        hook, token = self.hook_with_token()
        r, trigger, publish = self.fire(token)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json(), {"ok": True})
        row = ChatMessage.objects.filter(topic=self.t1).order_by("-sequence").first()
        self.assertEqual(row.content, "@Sara the build is red")
        self.assertEqual(row.sender, self.sara)              # the hook acts as its creator
        self.assertEqual((row.metadata or {}).get("role"), "user")
        self.assertEqual(trigger.await_count, 1)
        kw = trigger.await_args.kwargs or {}
        args = trigger.await_args.args
        personas = kw.get("personas", args[0] if args else None)
        self.assertEqual([p.id for p in personas], [self.persona_sara.id])
        self.assertEqual(kw.get("triggered_by", None) or args[-1], self.sara)
        self.assertTrue(any(c.args[1].get("id") == str(row.id) and c.args[1].get("type") == "message" for c in publish.call_args_list))
        hook.refresh_from_db()
        self.assertEqual((hook.fire_count, hook.last_status, hook.last_error), (1, InboundHook.FireStatus.SUCCESS, ""))
        self.assertIsNotNone(hook.last_fired_at)

    def test_structured_data_rides_along_as_a_fenced_block(self):
        _, token = self.hook_with_token()
        r, _, _ = self.fire(token, {"text": "deploy failed", "data": {"service": "api", "exit": 3}})
        self.assertEqual(r.status_code, 200, r.content)
        row = ChatMessage.objects.filter(topic=self.t1).order_by("-sequence").first()
        self.assertTrue(row.content.startswith("@Sara deploy failed\n\n```json\n"))
        self.assertIn('"service": "api"', row.content)
        self.assertTrue(row.content.endswith("```"))

    def test_the_endpoint_matrix(self):
        hook, token = self.hook_with_token()
        # Unknown token: 404, and nothing about whether it ever existed.
        r, trigger, _ = self.fire("nope-not-a-token")
        self.assertEqual(r.status_code, 404)
        trigger.assert_not_awaited()
        # Empty and oversize text.
        self.assertEqual(self.fire(token, {"text": "   "})[0].status_code, 400)
        self.assertEqual(self.fire(token, {"text": "x" * 4001})[0].status_code, 413)
        self.assertEqual(self.fire(token, {"text": "ok", "data": {"big": "y" * 33_000}})[0].status_code, 413)
        # Paused: 409, and no message posted.
        before = ChatMessage.objects.filter(topic=self.t1).count()
        InboundHook.objects.filter(id=hook.id).update(is_paused=True)
        r, trigger, _ = self.fire(token)
        self.assertEqual(r.status_code, 409)
        trigger.assert_not_awaited()
        self.assertEqual(ChatMessage.objects.filter(topic=self.t1).count(), before)
        InboundHook.objects.filter(id=hook.id).update(is_paused=False)
        # The creator lost the right to call personas: 403, recorded on the hook, still nothing posted.
        self.demote_to_viewer(self.sara)
        r, trigger, _ = self.fire(token)
        self.assertEqual(r.status_code, 403)
        trigger.assert_not_awaited()
        self.assertEqual(ChatMessage.objects.filter(topic=self.t1).count(), before)
        hook.refresh_from_db()
        self.assertEqual(hook.last_status, InboundHook.FireStatus.FAILED)
        self.assertIn("call personas", hook.last_error)

    def test_archiving_the_chat_or_the_project_stops_its_hooks(self):
        """A soft delete cascades to nothing, so the fire path has to ask about the parents."""
        hook, token = self.hook_with_token()
        self.assertEqual(self.fire(token)[0].status_code, 200)
        self.t1.soft_delete()
        r, trigger, _ = self.fire(token)
        self.assertEqual(r.status_code, 404)   # and says nothing about the hook having existed
        trigger.assert_not_awaited()
        self.t1.is_active = True
        self.t1.save(update_fields=["is_active"])
        self.assertEqual(self.fire(token)[0].status_code, 200)
        self.p1.soft_delete()
        self.assertEqual(self.fire(token)[0].status_code, 404)

    def test_the_sender_s_text_cannot_write_its_own_markdown(self):
        _, token = self.hook_with_token()
        r, _, _ = self.fire(token, {"text": "all good\n```\nnot really a code block\n```", "data": {"k": "v"}})
        self.assertEqual(r.status_code, 200, r.content)
        row = ChatMessage.objects.filter(topic=self.t1).order_by("-sequence").first()
        # Only the block this server wrote opens at the start of a line.
        opens = [line for line in row.content.splitlines() if line.startswith("```")]
        self.assertEqual(opens, ["```json", "```"])

    def test_a_rate_limiter_that_is_down_closes_the_door(self):
        _, token = self.hook_with_token()

        class Broken:
            async def incr(self, key, ttl):
                raise RuntimeError("redis is gone")

        with patch("scheduling.hooks.signal_store", return_value=Broken()):
            r, trigger, _ = self.fire(token)
        self.assertEqual(r.status_code, 503)
        trigger.assert_not_awaited()

    def test_a_paused_hook_and_a_bad_payload_still_spend_the_budget(self):
        hook, token = self.hook_with_token()
        InboundHook.objects.filter(id=hook.id).update(is_paused=True)
        for _ in range(hook_svc.FIRES_PER_MINUTE):
            self.assertEqual(self.fire(token)[0].status_code, 409)
        # The budget is gone even though not one fire was accepted.
        self.assertEqual(self.fire(token)[0].status_code, 429)

    def test_a_persona_without_a_model_is_a_failed_fire_not_a_silent_success(self):
        # The trigger path skips a modelless persona without a word, so the hook
        # used to answer ok and count a success while nothing was ever asked.
        hook, token = self.hook_with_token()
        from nucleus.models import ModelConfig
        ModelConfig.objects.filter(id=hook.persona.model_id).update(is_active=False)
        r, trigger, _ = self.fire(token)
        self.assertEqual(r.status_code, 403, r.content)
        self.assertIn("no working model", r.json()["detail"])
        trigger.assert_not_awaited()
        hook.refresh_from_db()
        self.assertEqual(hook.last_status, InboundHook.FireStatus.FAILED)
        self.assertEqual(hook.fire_count, 0)

    def test_a_refused_trigger_is_recorded_and_told_to_the_sender(self):
        hook, token = self.hook_with_token()
        refusal = [{"persona_id": str(hook.persona_id), "name": "Sara", "code": "x", "message": "Sara will not answer this.", "resets_at": None}]
        with patch("scheduling.hooks.chat_api._trigger_personas", new_callable=AsyncMock, return_value=refusal), \
             patch("chat.services.publish_async", new_callable=AsyncMock), \
             patch("chat.services.embed_message_async", new_callable=AsyncMock):
            r = Client().post(f"/api/v1/hooks/{token}/", data={"text": "the build is red"}, content_type="application/json")
        self.assertEqual(r.status_code, 409, r.content)
        self.assertEqual(r.json()["detail"], "Sara will not answer this.")
        hook.refresh_from_db()
        self.assertEqual((hook.last_status, hook.last_error), (InboundHook.FireStatus.FAILED, "Sara will not answer this."))

    def test_a_hook_is_rate_limited_per_hook_and_says_when_to_retry(self):
        _, token = self.hook_with_token()
        for i in range(hook_svc.FIRES_PER_MINUTE):
            self.assertEqual(self.fire(token)[0].status_code, 200, f"fire {i + 1}")
        r, trigger, _ = self.fire(token)
        self.assertEqual(r.status_code, 429)
        trigger.assert_not_awaited()
        self.assertEqual(r.headers.get("Retry-After"), "60")
        # Another hook has its own budget.
        _, other = self.hook_with_token()
        self.assertEqual(self.fire(other)[0].status_code, 200)
