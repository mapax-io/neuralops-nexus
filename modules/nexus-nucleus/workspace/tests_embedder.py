"""
Step 3 — the per-project embedder + the reindex flow
(docs/NUCLEUS-REVAMP.md Step 3; handoff change 10, decisions 3/4/8).

Only a COMPANY owner/admin changes a project's embedder; saving it locks the
project and queues the rebuild; while it rebuilds, persona triggers in the
project are refused with a worded message; the Celery task polls the engine
until the index is active again and then unlocks.
"""
from unittest.mock import patch

from chat.tests import MentionRightFixture
from nucleus.models import Project

SPEC = {"provider": "openai_compatible", "model_id": "text-embedding-3-small", "api_base": "https://x.example/v1"}


class EmbedderEndpointTests(MentionRightFixture):
    def put(self, user, body):
        with patch("intelligence.tasks.reindex_project.delay") as queued:
            r = self.call("put", f"/api/v1/projects/{self.p1.id}/embedder/", user, body)
        return r, queued

    def test_only_a_company_owner_or_admin_changes_it(self):
        r, queued = self.put(self.sara, {"embedder": SPEC})  # a Member may not
        self.assertEqual(r.status_code, 403, r.content)
        queued.assert_not_called()
        r, queued = self.put(self.owner, {"embedder": SPEC})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["reindex_status"], "building")
        queued.assert_called_once_with(str(self.p1.id))
        self.p1.refresh_from_db()
        self.assertEqual((self.p1.embedder, self.p1.reindex_status), (SPEC, "building"))

    def test_a_bad_spec_is_refused_with_the_reason(self):
        r, queued = self.put(self.owner, {"embedder": {"provider": "clippy", "model_id": "x"}})
        self.assertEqual(r.status_code, 400)
        self.assertIn("provider", r.json()["detail"])
        r, queued = self.put(self.owner, {"embedder": {"provider": "fastembed", "model_id": " "}})
        self.assertEqual(r.status_code, 400)
        self.assertIn("model_id", r.json()["detail"])
        queued.assert_not_called()

    def test_null_means_back_to_the_system_default_and_still_rebuilds(self):
        Project.objects.filter(id=self.p1.id).update(embedder=SPEC)
        r, queued = self.put(self.owner, {"embedder": None})
        self.assertEqual(r.status_code, 200, r.content)
        self.p1.refresh_from_db()
        self.assertIsNone(self.p1.embedder)
        queued.assert_called_once()

    def test_one_rebuild_at_a_time(self):
        Project.objects.filter(id=self.p1.id).update(reindex_status="building")
        r, queued = self.put(self.owner, {"embedder": SPEC})
        self.assertEqual(r.status_code, 409)
        queued.assert_not_called()

    def test_the_setting_is_readable_with_its_status(self):
        Project.objects.filter(id=self.p1.id).update(embedder=SPEC, reindex_status="failed")
        r = self.call("get", f"/api/v1/projects/{self.p1.id}/embedder/", self.owner)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json(), {"embedder": SPEC, "reindex_status": "failed"})

    def test_personas_are_refused_while_the_project_rebuilds(self):
        Project.objects.filter(id=self.p1.id).update(reindex_status="building")
        r, trigger, _ = self.send(self.sara, "@Sara hello")
        self.assertEqual(r.status_code, 200, r.content)
        refusals = r.json()["refusals"]
        self.assertEqual([x["code"] for x in refusals], ["reindexing"])
        self.assertIn("rebuilt", refusals[0]["message"])
        trigger.assert_not_called()


class ReindexTaskTests(MentionRightFixture):
    """The Celery driver: start → poll → unlock; a refusal or a timeout marks failed."""

    def run_task(self, start=(True, "building"), statuses=()):
        from intelligence import tasks
        Project.objects.filter(id=self.p1.id).update(reindex_status="building")
        seq = list(statuses)
        with patch("chat.nexus_ai.NexusAIClient.start_reindex", return_value=start) as started, \
             patch("chat.nexus_ai.NexusAIClient.reindex_status", side_effect=seq), \
             patch("time.sleep", return_value=None), \
             patch.object(tasks, "REINDEX_MAX_POLLS", len(seq)):
            out = tasks.reindex_project(str(self.p1.id))
        self.p1.refresh_from_db()
        return out, started

    def test_a_finished_rebuild_unlocks_the_project(self):
        out, started = self.run_task(statuses=[{"status": "building", "done": 1, "total": 2},
                                               {"status": "active", "done": 2, "total": 2}])
        self.assertEqual(out, "active")
        self.assertEqual(self.p1.reindex_status, "")
        # The system default rides when the project has no spec of its own.
        self.assertEqual(started.call_args.args[2]["provider"], "fastembed")

    def test_a_refused_start_marks_the_project_failed(self):
        out, _ = self.run_task(start=(False, "vector store is not configured"), statuses=[])
        self.assertTrue(out.startswith("failed"))
        self.assertEqual(self.p1.reindex_status, "failed")

    def test_a_rebuild_that_never_finishes_marks_failed(self):
        out, _ = self.run_task(statuses=[{"status": "building", "done": 0, "total": 9}] * 3)
        self.assertEqual(out, "failed: timed out")
        self.assertEqual(self.p1.reindex_status, "failed")
