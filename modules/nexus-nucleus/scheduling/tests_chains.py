"""
Step 7 (docs/NUCLEUS-REVAMP.md) — chains: runbooks grown up.

What these prove, ruling by ruling, over the real loop (only the AI trigger is
faked, exactly like scheduling/tests.py):
  1. same tables — everything here runs on Runbook/RunbookRun;
  2. the one optional supervisor reviews every stage, verdicts recorded;
  3. bounded redo — the redo prompt carries the notes, exhaustion falls to
     on_failure, redo_limit is validated 0..2;
  4. checkpoints — the run parks WAITING, the starter or the four roles
     answer, the answer rides the next step's context, 24h expiry applies
     the checkpoint's own on_failure, stop works while waiting;
  5. schedules stay simple — a checkpoint chain cannot be scheduled, and
     every fired step still says interactive=False;
  6. the gateway's chain tools run with rights-as-the-person;
  7. every new project is born with the (step-less, unrunnable) template.
"""
import uuid
from datetime import timedelta
from unittest.mock import AsyncMock, patch

from asgiref.sync import sync_to_async
from django.utils import timezone

from nucleus.models import ChatMessage, Runbook, RunbookRun
from scheduling import runbooks
from scheduling.runbooks import execute_run
from scheduling.tests import RunbookFixture


class ChainFixture(RunbookFixture):
    """RunbookFixture plus a review-aware fake worker."""

    def chain(self, steps=None, supervisor=None, redo_limit=1, title="Weekly ops update"):
        body = {"title": title, "description": "", "steps": steps or self.steps, "redo_limit": redo_limit}
        if supervisor is not None:
            body["supervisor_id"] = str(supervisor.id)
        r = self.call("post", self.runs_path, self.owner, body)
        self.assertEqual(r.status_code, 200, r.content)
        return Runbook.objects.get(id=r.json()["id"])

    def checkpoint_step(self, question="Ship it?", on_failure="stop"):
        return {"kind": "checkpoint", "question": question, "on_failure": on_failure}

    def execute_chain(self, run_id, outcomes=None, reviews=None):
        """
        Like RunbookFixture.execute, but review calls (runbook_run.review) are
        answered from `reviews` in order (verbatim reply text, e.g. "REDO\\nadd
        numbers"); stage calls from `outcomes` per 1-based step. Returns every
        trigger's kwargs.
        """
        from chat.services import create_ai_message

        outcomes = outcomes or {}
        reviews = list(reviews or [])
        calls: list[dict] = []
        attempts: dict[int, int] = {}

        def reply(kw, content, status="completed"):
            msg = create_ai_message(kw["company"], kw["project"], kw["topic"], kw["persona"],
                                    triggered_by=kw.get("triggered_by"), runbook_run=kw["runbook_run"])
            ChatMessage.objects.filter(id=msg["id"]).update(status=status, content=content)
            return msg["id"]

        async def fake_trigger(**kw):
            calls.append(kw)
            rr = kw.get("runbook_run") or {}
            if rr.get("review"):
                text = reviews.pop(0) if reviews else "APPROVE\nLooks right."
                return await sync_to_async(reply)(kw, text)
            step = rr["step"]
            attempts[step] = attempts.get(step, 0) + 1
            planned = outcomes.get(step, "done")
            outcome = planned[min(attempts[step], len(planned)) - 1] if isinstance(planned, list) else planned
            status = {"done": "completed", "failed": "failed"}[outcome]
            return await sync_to_async(reply)(kw, f"reply {step} try {attempts[step]}", status=status)

        with patch("chat.services.trigger_ai_response_async", new=AsyncMock(side_effect=fake_trigger)), \
             patch("chat.services.publish"), patch("chat.services.publish_async", new_callable=AsyncMock):
            execute_run(str(run_id))
        return calls

    def started(self, runbook, user=None):
        r, _ = self.start(runbook, user)
        self.assertEqual(r.status_code, 200, r.content)
        return RunbookRun.objects.get(id=r.json()["id"])


class ChainDefinitionTests(ChainFixture):
    """Rulings 1+2+3 (the definition side) and 7."""

    def test_supervisor_and_redo_round_trip_and_are_validated(self):
        chain = self.chain(supervisor=self.persona_bob, redo_limit=2)
        r = self.call("get", self.runs_path, self.owner)
        row = next(x for x in r.json() if x["id"] == str(chain.id))
        self.assertEqual((row["supervisor_id"], row["supervisor_name"], row["redo_limit"], row["has_checkpoint"]),
                         (str(self.persona_bob.id), "Bob", 2, False))
        # Clearing, and the bounds.
        r = self.call("patch", f"{self.runs_path}{chain.id}/", self.owner, {"clear_supervisor": True})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertIsNone(r.json()["supervisor_id"])
        self.assertEqual(self.call("patch", f"{self.runs_path}{chain.id}/", self.owner, {"redo_limit": 3}).status_code, 400)
        body = {"title": "x", "steps": self.steps, "supervisor_id": str(uuid.uuid4())}
        self.assertIn("supervisor", self.call("post", self.runs_path, self.owner, body).json()["detail"])

    def test_checkpoint_steps_are_validated(self):
        chain = self.chain(steps=[self.steps[0], self.checkpoint_step()])
        self.assertTrue(runbooks.has_checkpoint(chain))
        r = self.call("get", self.runs_path, self.owner)
        row = next(x for x in r.json() if x["id"] == str(chain.id))
        self.assertTrue(row["has_checkpoint"])
        self.assertEqual((row["steps"][1]["kind"], row["steps"][1]["question"]), ("checkpoint", "Ship it?"))
        for bad in ({"kind": "checkpoint"},                                 # no question
                    {"kind": "checkpoint", "question": "x", "on_failure": "retry"},  # nothing to retry
                    {"kind": "laser", "question": "x"}):                    # unknown kind
            r = self.call("post", self.runs_path, self.owner, {"title": "b", "steps": [bad]})
            self.assertEqual(r.status_code, 400, bad)

    def test_a_checkpoint_chain_cannot_be_scheduled(self):
        """Ruling 5, the owner's words: schedules are simple — no answer query."""
        chain = self.chain(steps=[self.steps[0], self.checkpoint_step()])
        path = f"/api/v1/projects/{self.p1.id}/channels/{self.c1.id}/topics/{self.t1.id}/schedules/"
        body = {"runbook_id": str(chain.id), "schedule_kind": "interval", "interval_every": 1, "interval_period": "days"}
        r = self.call("post", path, self.owner, body)
        self.assertEqual(r.status_code, 400, r.content)
        self.assertIn("checkpoint", r.json()["detail"])

    def test_every_new_project_is_born_with_the_template_which_cannot_run_yet(self):
        """Ruling 7 — and its honest limit: no personas at birth, so no steps."""
        from workspace import services as ws_svc
        delta = ws_svc.create_project(self.company, self.owner, "Delta")
        rows = runbooks.list_runbooks(delta)
        self.assertEqual([rb.title for rb in rows], ["Draft and review"])
        self.assertEqual(rows[0].steps, [])
        path = f"/api/v1/projects/{delta.id}/runbooks/{rows[0].id}/run/"
        r = self.call("post", path, self.owner, {"topic_id": None, "channel_id": None})
        self.assertEqual(r.status_code, 400, r.content)
        self.assertIn("no steps", r.json()["detail"])


class SupervisorTests(ChainFixture):
    """Rulings 2+3, over the real loop."""

    def test_approvals_let_the_run_finish_and_reviews_are_unattended(self):
        chain = self.chain(steps=self.steps[:2], supervisor=self.persona_bob)
        run = self.started(chain)
        calls = self.execute_chain(run.id, reviews=["APPROVE\nSolid.", "APPROVED — good."])
        run.refresh_from_db()
        self.assertEqual(run.status, "done", run.error)
        self.assertEqual([s["verdict"] for s in run.step_results], ["approve", "approve"])
        reviews = [c for c in calls if (c.get("runbook_run") or {}).get("review")]
        self.assertEqual(len(reviews), 2)
        self.assertTrue(all(str(c["persona"].id) == str(self.persona_bob.id) for c in reviews))
        self.assertTrue(all(c["interactive"] is False for c in calls))  # ruling 5: nobody is watching

    def test_redo_reruns_the_stage_with_the_notes_then_passes(self):
        chain = self.chain(steps=self.steps[:1], supervisor=self.persona_bob, redo_limit=1)
        run = self.started(chain)
        calls = self.execute_chain(run.id, reviews=["REDO\nAdd the May numbers.", "APPROVE"])
        run.refresh_from_db()
        self.assertEqual(run.status, "done", run.error)
        self.assertEqual((run.step_results[0]["redos"], run.step_results[0]["verdict"]), (1, "approve"))
        stages = [c for c in calls if not (c.get("runbook_run") or {}).get("review")]
        self.assertEqual(len(stages), 2)  # the stage, then its redo
        self.assertIn("Add the May numbers.", stages[1]["user_message"])

    def test_redo_exhaustion_and_fail_fall_to_on_failure(self):
        # stop (the default): the run fails with the reviewer's reason.
        chain = self.chain(steps=self.steps[:1], supervisor=self.persona_bob, redo_limit=1)
        run = self.started(chain)
        self.execute_chain(run.id, reviews=["REDO\nmore", "REDO\nstill wrong"])
        run.refresh_from_db()
        self.assertEqual(run.status, "failed")
        self.assertIn("reviewer", run.error)
        # skip: a FAIL verdict is carried past, the run finishes unclean.
        skip_step = {**self.steps[0], "on_failure": "skip"}
        chain2 = self.chain(steps=[skip_step, self.steps[1]], supervisor=self.persona_bob, title="Skippy")
        run2 = self.started(chain2)
        self.execute_chain(run2.id, reviews=["FAIL\nNot its job.", "APPROVE"])
        run2.refresh_from_db()
        self.assertEqual(run2.status, "done", run2.error)
        self.assertEqual(run2.step_results[0]["status"], "skipped")
        self.assertEqual(runbooks.skipped_count(run2), 1)

    def test_an_unclear_verdict_lets_the_stage_stand(self):
        chain = self.chain(steps=self.steps[:1], supervisor=self.persona_bob)
        run = self.started(chain)
        self.execute_chain(run.id, reviews=["Looks broadly fine to me."])
        run.refresh_from_db()
        self.assertEqual(run.status, "done", run.error)
        self.assertEqual(run.step_results[0]["verdict"], "unclear")


class CheckpointTests(ChainFixture):
    """Ruling 4, end to end."""

    def waiting_run(self, on_failure="stop"):
        chain = self.chain(steps=[self.steps[0], self.checkpoint_step(on_failure=on_failure), self.steps[2]])
        run = self.started(chain)  # started by sara
        self.execute_chain(run.id)
        run.refresh_from_db()
        self.assertEqual(run.status, "waiting", run.error)
        return run

    def answer(self, run, user, answer="Ship it."):
        path = f"{self.runs_path}runs/{run.id}/checkpoint/"
        with patch("scheduling.tasks.run_runbook.delay") as delay:
            r = self.call("post", path, user, {"answer": answer})
        return r, delay

    def test_the_run_parks_then_the_answer_resumes_it_with_the_answer_in_context(self):
        run = self.waiting_run()
        self.assertEqual((run.checkpoint["index"], run.checkpoint["question"]), (1, "Ship it?"))
        # A viewer is neither the starter nor one of the four roles.
        r, delay = self.answer(run, self.vera)
        self.assertEqual(r.status_code, 403, r.content)
        delay.assert_not_called()
        # The starter answers (sara holds no project.update — the starter rule).
        r, delay = self.answer(run, self.sara, "Ship it, but rename the file.")
        self.assertEqual(r.status_code, 200, r.content)
        delay.assert_called_once_with(str(run.id))
        run.refresh_from_db()
        self.assertEqual((run.status, run.current_step, run.checkpoint), ("queued", 2, None))
        self.assertEqual(run.step_results[-1]["status"], "answered")
        self.assertIn("rename the file", run.context)
        # Answering twice: the claim lost, 409.
        r, _ = self.answer(run, self.owner)
        self.assertEqual(r.status_code, 409, r.content)
        # The resumed task finishes the rest; step 3 builds on the answer.
        calls = self.execute_chain(run.id)
        run.refresh_from_db()
        self.assertEqual(run.status, "done", run.error)
        self.assertIn("rename the file", calls[0]["step_context"])
        self.assertEqual(len(run.step_results), 3)

    def test_expiry_applies_the_checkpoints_own_on_failure(self):
        # stop: the run fails with the expiry reason.
        run = self.waiting_run()
        with patch("scheduling.tasks.run_runbook.delay") as delay, \
             patch("chat.services.publish"), patch("chat.services.publish_async", new_callable=AsyncMock):
            runbooks.expire_waiting_run(run)
        delay.assert_not_called()
        run.refresh_from_db()
        self.assertEqual(run.status, "failed")
        self.assertIn("expired", run.error)
        self.assertEqual(run.step_results[-1]["status"], "expired")
        # skip: the run is re-enqueued past the checkpoint.
        run2 = self.waiting_run(on_failure="skip")
        with patch("scheduling.tasks.run_runbook.delay") as delay, \
             patch("chat.services.publish"), patch("chat.services.publish_async", new_callable=AsyncMock):
            runbooks.expire_waiting_run(run2)
        delay.assert_called_once_with(str(run2.id))
        run2.refresh_from_db()
        self.assertEqual((run2.status, run2.current_step, run2.checkpoint), ("queued", 2, None))

    def test_the_hourly_task_expires_only_runs_past_the_window(self):
        from scheduling.tasks import expire_waiting_checkpoints
        old = self.waiting_run()
        fresh = self.waiting_run()
        RunbookRun.objects.filter(id=old.id).update(updated_at=timezone.now() - timedelta(hours=25))
        with patch("scheduling.runbooks.expire_waiting_run") as expire:
            expire_waiting_checkpoints()
        self.assertEqual([str(c.args[0].id) for c in expire.call_args_list], [str(old.id)])
        self.assertTrue(fresh.id)  # untouched

    def test_stop_works_while_waiting(self):
        run = self.waiting_run()
        with patch("chat.services.publish"), patch("chat.services.publish_async", new_callable=AsyncMock):
            self.assertEqual(runbooks.stop_run(run, self.owner), "stopped")
        run.refresh_from_db()
        self.assertEqual((run.status, run.checkpoint), ("stopped", None))

    def test_a_schedule_fire_refuses_a_chain_edited_into_a_checkpoint(self):
        """Ruling 5's second fence — the guard at fire time, not only at creation."""
        from nucleus.models import PersonaSchedule
        from scheduling.tasks import fire_persona_schedule
        chain = self.chain(steps=[self.steps[0]])
        schedule = PersonaSchedule.objects.create(
            company=self.company, project=self.p1, topic=self.t1, runbook=chain,
            created_by=self.owner, schedule_kind="interval", interval_every=1, interval_period="days",
            query_text="", label="", timezone="UTC",
        )
        # Edited AFTER scheduling: a checkpoint sneaks in.
        chain.steps = [self.steps[0], self.checkpoint_step()]
        chain.save(update_fields=["steps"])
        with patch("scheduling.tasks.run_runbook.delay") as delay, \
             patch("chat.services.publish"), patch("chat.services.publish_async", new_callable=AsyncMock):
            fire_persona_schedule(str(schedule.id))
        delay.assert_not_called()
        schedule.refresh_from_db()
        self.assertEqual(schedule.last_status, PersonaSchedule.RunStatus.FAILED)
        self.assertIn("checkpoint", schedule.last_error)


class GatewayChainToolTests(ChainFixture):
    """Ruling 6: the three tools on the Step 6 door, rights-as-the-person."""

    def token_for(self, user):
        r = self.call("post", "/api/v1/gateway/tokens/", self.owner, {"name": f"for-{user.username}", "user_id": str(user.id)})
        self.assertEqual(r.status_code, 200, r.content)
        return r.json()["token"]

    def tool(self, token, name, arguments):
        import json as jsonlib
        from django.test import Client
        body = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": arguments}}
        r = Client().post("/api/v1/mcp/", data=jsonlib.dumps(body), content_type="application/json",
                          HTTP_AUTHORIZATION=f"Bearer {token}")
        self.assertEqual(r.status_code, 200, r.content)
        result = r.json()["result"]
        text = result["content"][0]["text"]
        return result["isError"], (text if result["isError"] else jsonlib.loads(text))

    def test_the_three_tools_list_run_and_follow_a_chain(self):
        chain = self.chain(steps=self.steps[:1], supervisor=self.persona_bob)
        sara_token = self.token_for(self.sara)
        is_error, rows = self.tool(sara_token, "list_chains", {"project_id": str(self.p1.id)})
        self.assertFalse(is_error, rows)
        row = next(x for x in rows if x["id"] == str(chain.id))
        self.assertEqual((row["title"], row["steps"], row["supervisor"]), ("Weekly ops update", 1, "Bob"))
        with patch("scheduling.tasks.run_runbook.delay") as delay:
            is_error, out = self.tool(sara_token, "run_chain",
                                      {"chain_id": str(chain.id), "topic_id": str(self.t1.id)})
        self.assertFalse(is_error, out)
        self.assertEqual(out["status"], "queued")
        delay.assert_called_once_with(out["run_id"])
        is_error, status = self.tool(sara_token, "chain_status", {"run_id": out["run_id"]})
        self.assertFalse(is_error, status)
        self.assertEqual((status["status"], status["step_count"]), ("queued", 1))

    def test_a_viewer_sees_chains_but_cannot_run_one(self):
        chain = self.chain(steps=self.steps[:1])
        vera_token = self.token_for(self.vera)
        is_error, rows = self.tool(vera_token, "list_chains", {"project_id": str(self.p1.id)})
        self.assertFalse(is_error, rows)
        with patch("scheduling.tasks.run_runbook.delay") as delay:
            is_error, text = self.tool(vera_token, "run_chain",
                                       {"chain_id": str(chain.id), "topic_id": str(self.t1.id)})
        self.assertTrue(is_error)
        delay.assert_not_called()
