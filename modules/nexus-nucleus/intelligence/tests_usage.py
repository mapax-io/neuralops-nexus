"""
intelligence/tests_usage.py

Usage rows written by nucleus from the worker's events, monthly budgets on a
model (tokens and dollars, warn at 90 %, stop at 100 %), and what a stopped
model refuses. Separate module from tests.py so it runs while that file's
older OAuth fixture is broken (OPEN-ITEMS).
"""
import json
import uuid
from datetime import timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, patch

from asgiref.sync import async_to_sync
from django.test import Client, override_settings
from django.utils import timezone

from chat.tests import MentionRightFixture
from intelligence import usage as usage_svc
from intelligence.services import update_model_config
from nucleus.models import AIRequestLog, ChatMessage, PersonaSchedule
from scheduling.tasks import fire_persona_schedule


def usage_payload(**over) -> dict:
    base = {"input_tokens": 100, "output_tokens": 50, "cache_read_tokens": 0, "cache_write_tokens": 0, "requests": 1, "tool_calls": 0, "cost_usd": 0.01}
    base.update(over)
    return base


class UsageFixture(MentionRightFixture):
    def record(self, *, persona=None, actor=None, tokens=150, cost=0.01, hop=0, status="success", when=None):
        row = usage_svc.record_ai_request(
            self.company, persona=persona or self.persona_sara, model_config=self.model_config,
            actor_id=str((actor or self.sara).id), topic=self.t1, msg_id=str(uuid.uuid4()), job_id="job", hop=hop,
            usage=usage_payload(input_tokens=tokens, output_tokens=0, cost_usd=cost) if status == "success" else None,
            latency_ms=10, status=status, error=None if status == "success" else "boom",
        )
        if when is not None:
            AIRequestLog.objects.filter(id=row.id).update(created_at=when)
            row.refresh_from_db()
        return row

    def system_messages(self, needle: str):
        return ChatMessage.objects.filter(topic=self.t1, message_type="system", content__icontains=needle)


class RecordTests(UsageFixture):
    def test_a_row_carries_actor_model_topic_and_counts_and_never_the_prompt(self):
        row = self.record()
        self.assertEqual((row.actor, row.model_config, row.topic, row.persona), (self.sara, self.model_config, self.t1, self.persona_sara))
        self.assertEqual((row.provider, row.model_id), ("openai", "gpt-test"))
        self.assertEqual((row.prompt_tokens, row.completion_tokens, row.requests, row.total_tokens), (150, 0, 1, 150))
        self.assertEqual(row.cost_usd, Decimal("0.010000"))
        self.assertIsNone(row.prompt)
        self.assertIsNone(row.response)
        self.assertEqual(row.status, AIRequestLog.Status.SUCCESS)

    def test_a_failed_run_records_the_error_without_usage(self):
        row = self.record(status="error")
        self.assertEqual((row.status, row.error, row.total_tokens, row.cost_usd), (AIRequestLog.Status.ERROR, "boom", 0, None))


class TotalsAndBudgetTests(UsageFixture):
    def test_month_totals_count_this_month_only_and_flag_an_incomplete_cost(self):
        self.record(tokens=150, cost=0.01)
        self.record(tokens=150, cost=None)
        self.record(tokens=150, cost=0.01, when=timezone.now() - timedelta(days=40))
        month = usage_svc.month_totals(self.model_config)
        self.assertEqual((month["tokens"], month["requests"], month["cost_usd"], month["cost_complete"]), (300, 2, Decimal("0.010000"), False))
        self.assertEqual(usage_svc.all_time_totals(self.model_config)["tokens"], 450)

    def test_tokens_warn_at_90_percent_and_stop_at_100(self):
        self.model_config.monthly_token_budget = 1000
        self.model_config.save()
        self.record(tokens=900)
        state = usage_svc.budget_state(self.model_config)
        self.assertEqual((state["state"], state["tokens_remaining"]), ("warn", 100))
        self.assertFalse(usage_svc.is_model_stopped(self.model_config))
        self.record(tokens=100)
        state = usage_svc.budget_state(self.model_config)
        self.assertEqual((state["state"], state["tokens_remaining"]), ("stopped", 0))
        self.assertTrue(usage_svc.is_model_stopped(self.model_config))

    def test_dollars_enforce_only_when_every_row_this_month_has_a_cost(self):
        self.model_config.monthly_cost_budget_usd = Decimal("1.00")
        self.model_config.save()
        self.record(tokens=10, cost=0.95)
        self.record(tokens=10, cost=0.10)
        self.assertEqual(usage_svc.budget_state(self.model_config)["state"], "stopped")
        self.record(tokens=10, cost=None)  # one unpriced call: the dollar side can no longer be trusted
        state = usage_svc.budget_state(self.model_config)
        self.assertEqual((state["state"], state["cost_complete"]), ("ok", False))

    def test_evaluate_posts_one_warning_and_one_stop_per_month(self):
        self.model_config.monthly_token_budget = 1000
        self.model_config.save()
        with patch("chat.services.publish") as publish:
            self.record(tokens=900)
            usage_svc.evaluate_budget(self.model_config, self.t1)
            usage_svc.evaluate_budget(self.model_config, self.t1)
            self.assertEqual(self.system_messages("90%").count(), 1)
            self.record(tokens=100)
            usage_svc.evaluate_budget(self.model_config, self.t1)
            usage_svc.evaluate_budget(self.model_config, self.t1)
            self.assertEqual(self.system_messages("monthly budget").count(), 2)  # the warning and the stop
            self.assertEqual(self.system_messages("won't answer").count(), 1)
            self.assertEqual(publish.call_count, 2)
        self.model_config.refresh_from_db()
        today = timezone.now().date()
        self.assertEqual((self.model_config.budget_warned_at, self.model_config.budget_stopped_at), (today.replace(day=1), today.replace(day=1)))

    def test_changing_a_budget_clears_the_stop_and_zero_clears_the_budget(self):
        self.model_config.monthly_token_budget = 100
        self.model_config.save()
        self.record(tokens=120)
        with patch("chat.services.publish"):
            usage_svc.evaluate_budget(self.model_config, self.t1)
        self.assertTrue(usage_svc.is_model_stopped(self.model_config))
        config = update_model_config(self.company, str(self.model_config.id), {"monthly_token_budget": 5000})
        self.assertEqual((config.monthly_token_budget, config.budget_warned_at, config.budget_stopped_at), (5000, None, None))
        self.assertFalse(usage_svc.is_model_stopped(config))
        config = update_model_config(self.company, str(self.model_config.id), {"monthly_token_budget": 0, "monthly_cost_budget_usd": 0})
        self.assertIsNone(config.monthly_token_budget)
        self.assertIsNone(config.monthly_cost_budget_usd)


class TriggerRefusalTests(UsageFixture):
    def stop_the_model(self):
        self.model_config.monthly_token_budget = 100
        self.model_config.save()
        self.record(tokens=120)

    def test_a_persona_on_a_stopped_model_is_refused_and_the_message_still_posts(self):
        self.stop_the_model()
        r, trigger, swarm, publish = self.send(self.sara, "@Sara hello")
        self.assertEqual(r.status_code, 200, r.content)
        body = r.json()
        self.assertEqual([(x["name"], x["code"]) for x in body["refusals"]], [("Sara", "model_budget")])
        self.assertIn("monthly budget", body["refusals"][0]["message"])
        self.assertIsNotNone(body["refusals"][0]["resets_at"])
        trigger.assert_not_called()
        self.assertTrue(ChatMessage.objects.filter(id=body["message"]["id"], sender=self.sara).exists())

    def test_a_scheduled_fire_on_a_stopped_model_is_skipped(self):
        self.stop_the_model()
        path = f"/api/v1/projects/{self.p1.id}/channels/{self.c1.id}/topics/{self.t1.id}/schedules/"
        body = {"persona_id": str(self.persona_sara.id), "query_text": "daily summary", "schedule_kind": "interval", "interval_every": 1, "interval_period": "days"}
        with patch("authn.auth.verify_supabase_token", return_value={"email": self.sara.email}), patch("scheduling.api.chat_svc.publish"):
            self.assertEqual(Client().post(path, data=body, content_type="application/json", HTTP_AUTHORIZATION="Bearer t").status_code, 200)
        schedule = PersonaSchedule.objects.get()
        with patch("chat.services.trigger_ai_response_async", new_callable=AsyncMock) as trigger, patch("chat.services.publish"):
            fire_persona_schedule(str(schedule.id))
        trigger.assert_not_called()
        schedule.refresh_from_db()
        self.assertEqual(schedule.last_status, PersonaSchedule.RunStatus.FAILED)
        self.assertIn("budget", schedule.last_error)
        self.assertEqual(self.system_messages("skipped").count(), 1)


# ── The relay writes the rows from the worker's events ─────────────────────────

class FakeResponse:
    status_code = 200
    def __init__(self, lines):
        self._lines = lines
    async def aiter_lines(self):
        for line in self._lines:
            yield line
    async def aread(self):
        return b""


class FakeClient:
    """httpx.AsyncClient with .stream() serving canned SSE lines; remembers the job it was sent."""
    sent: list = []
    lines: list = []
    def __init__(self, *a, **k): pass
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return False
    def stream(self, method, url, json=None, headers=None):
        FakeClient.sent.append({"url": url, "json": json})
        lines = FakeClient.lines
        class CM:
            async def __aenter__(self): return FakeResponse(lines)
            async def __aexit__(self, *a): return False
        return CM()


def sse(event: dict) -> str:
    return "data: " + json.dumps(event)


@override_settings(NEXUS_AI_URL="http://ai.test", INTERNAL_API_KEY="k")
class StreamRecordingTests(UsageFixture):
    def run_single(self, lines, actor=None):
        from chat import services as chat_svc
        FakeClient.sent, FakeClient.lines = [], lines
        with patch("chat.services.httpx.AsyncClient", FakeClient), \
             patch("chat.services.publish_async", new_callable=AsyncMock), \
             patch("chat.services.embed_message_async", new_callable=AsyncMock), \
             patch("chat.services.publish"):
            async_to_sync(chat_svc.trigger_ai_response_async)(
                company=self.company, project=self.p1, topic=self.t1, persona=self.persona_sara,
                user_message="hi", user_message_id=str(uuid.uuid4()), topic_id=str(self.t1.id), output_type="auto",
                actor_user_id=str((actor or self.sara).id),
            )

    def test_message_done_writes_one_row_with_the_actor_model_and_usage(self):
        self.run_single([
            sse({"type": "message_start", "id": "x"}),
            sse({"type": "message_delta", "id": "x", "delta": "Hi"}),
            sse({"type": "message_done", "id": "x", "content": "Hi", "output_type": "text", "render_as": "text", "usage": usage_payload(input_tokens=7, output_tokens=3, cost_usd=0.002)}),
        ])
        self.assertEqual(FakeClient.sent[0]["json"]["actor_user_id"], str(self.sara.id))
        row = AIRequestLog.objects.get()
        self.assertEqual((row.actor, row.model_config, row.persona, row.topic, row.hop), (self.sara, self.model_config, self.persona_sara, self.t1, 0))
        self.assertEqual((row.prompt_tokens, row.completion_tokens, row.cost_usd, row.status), (7, 3, Decimal("0.002000"), AIRequestLog.Status.SUCCESS))
        self.assertGreaterEqual(row.latency_ms, 0)

    def test_message_error_writes_a_failed_row_without_usage(self):
        self.run_single([sse({"type": "message_error", "id": "x", "error": "provider down"})])
        row = AIRequestLog.objects.get()
        self.assertEqual((row.status, row.error, row.total_tokens, row.cost_usd), (AIRequestLog.Status.ERROR, "provider down", 0, None))

    def test_a_done_without_usage_still_writes_a_row_with_zero_counts(self):
        self.run_single([sse({"type": "message_done", "id": "x", "content": "Hi", "output_type": "text", "render_as": "text"})])
        row = AIRequestLog.objects.get()
        self.assertEqual((row.status, row.total_tokens, row.cost_usd), (AIRequestLog.Status.SUCCESS, 0, None))

    def test_crossing_the_budget_on_a_reply_posts_the_notice_and_stops_the_model(self):
        self.model_config.monthly_token_budget = 100
        self.model_config.save()
        self.run_single([sse({"type": "message_done", "id": "x", "content": "Hi", "output_type": "text", "render_as": "text", "usage": usage_payload(input_tokens=120, output_tokens=0)})])
        self.assertEqual(self.system_messages("won't answer").count(), 1)
        self.assertTrue(usage_svc.is_model_stopped(self.model_config))

    def test_a_swarm_writes_one_row_per_hop_for_the_persona_that_ran_it(self):
        from chat import services as chat_svc
        FakeClient.sent, FakeClient.lines = [], [
            sse({"type": "message_start", "id": None, "persona_id": str(self.persona_sara.id)}),
            sse({"type": "message_delta", "id": None, "delta": "Sara here"}),
            sse({"type": "message_done", "id": None, "content": "Sara here", "output_type": "text", "render_as": "text", "usage": usage_payload(input_tokens=5, output_tokens=1), "hop": 0}),
            sse({"type": "message_start", "id": "sub2", "persona_id": str(self.persona_bob.id)}),
            sse({"type": "message_delta", "id": "sub2", "delta": "Bob here"}),
            sse({"type": "message_done", "id": "sub2", "content": "Bob here", "output_type": "text", "render_as": "text", "usage": usage_payload(input_tokens=9, output_tokens=2), "hop": 1}),
        ]
        with patch("chat.services.httpx.AsyncClient", FakeClient), \
             patch("chat.services.publish_async", new_callable=AsyncMock), \
             patch("chat.services.embed_message_async", new_callable=AsyncMock):
            async_to_sync(chat_svc.trigger_ai_swarm_response_async)(
                company=self.company, project=self.p1, topic=self.t1, personas=[self.persona_sara, self.persona_bob],
                user_message="compare", user_message_id=str(uuid.uuid4()), topic_id=str(self.t1.id), output_type="auto",
                actor_user_id=str(self.sara.id),
            )
        rows = list(AIRequestLog.objects.order_by("hop"))
        self.assertEqual([(r.hop, r.persona_id, r.prompt_tokens, r.actor_id) for r in rows],
                         [(0, self.persona_sara.id, 5, self.sara.id), (1, self.persona_bob.id, 9, self.sara.id)])


class EndpointTests(UsageFixture):
    def get(self, user, path):
        with patch("authn.auth.verify_supabase_token", return_value={"email": user.email}):
            return Client().get(path, HTTP_AUTHORIZATION="Bearer t")

    def patch_config(self, user, body):
        with patch("authn.auth.verify_supabase_token", return_value={"email": user.email}):
            return Client().patch(f"/api/v1/model-configs/{self.model_config.id}/", data=body, content_type="application/json", HTTP_AUTHORIZATION="Bearer t")

    def test_usage_endpoint_reports_month_all_time_and_budget_per_visible_model(self):
        self.model_config.monthly_token_budget = 1000
        self.model_config.save()
        self.record(tokens=900, cost=0.5)
        r = self.get(self.owner, "/api/v1/model-configs/usage/")
        self.assertEqual(r.status_code, 200, r.content)
        body = r.json()[str(self.model_config.id)]
        self.assertEqual(body["month"]["total"], 900)
        self.assertEqual(body["month"]["cost_usd"], 0.5)
        self.assertTrue(body["month"]["cost_complete"])
        self.assertEqual(body["all_time"]["total"], 900)
        self.assertEqual((body["budget"]["tokens"], body["budget"]["tokens_remaining"], body["budget"]["state"]), (1000, 100, "warn"))
        self.assertIsNone(body["budget"]["cost_usd"])

    def test_budgets_patch_through_and_show_on_the_config(self):
        r = self.patch_config(self.owner, {"monthly_token_budget": 2000, "monthly_cost_budget_usd": 2.5})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual((r.json()["monthly_token_budget"], r.json()["monthly_cost_budget_usd"]), (2000, 2.5))
        r = self.patch_config(self.owner, {"monthly_token_budget": 0})
        self.assertIsNone(r.json()["monthly_token_budget"])

    def test_provider_remaining_is_openrouter_only(self):
        r = self.get(self.owner, f"/api/v1/model-configs/{self.model_config.id}/provider/")
        self.assertEqual(r.status_code, 404)
        self.model_config.provider = "openai_compatible"
        self.model_config.api_base = "https://openrouter.ai/api/v1"
        self.model_config.set_api_key("sk-or-test")
        self.model_config.save()
        with patch("intelligence.usage.fetch_openrouter_key", return_value={"limit": 10.0, "usage": 2.5, "limit_remaining": 7.5}) as fetch:
            r = self.get(self.owner, f"/api/v1/model-configs/{self.model_config.id}/provider/")
            self.assertEqual(r.status_code, 200, r.content)
            self.assertEqual(r.json(), {"limit": 10.0, "usage": 2.5, "remaining": 7.5})
            self.get(self.owner, f"/api/v1/model-configs/{self.model_config.id}/provider/")
        self.assertEqual(fetch.call_count, 1)  # cached
        fetch.assert_called_with("sk-or-test")


class InternalEndpointTests(UsageFixture):
    def test_the_worker_log_endpoint_no_longer_stores_prompt_or_response(self):
        from django.conf import settings
        body = {"job_id": "j", "msg_id": "m", "persona_id": str(self.persona_sara.id), "model_id": "gpt-test", "provider": "openai",
                "prompt": [{"role": "user", "content": "secret"}], "response": "also secret", "prompt_tokens": 3, "completion_tokens": 1, "status": "error", "error": "x"}
        r = Client().post("/api/v1/internal/ai-request-logs/", data=body, content_type="application/json", HTTP_X_INTERNAL_API_KEY=settings.INTERNAL_API_KEY)
        self.assertEqual(r.status_code, 201, r.content)
        row = AIRequestLog.objects.get()
        self.assertIsNone(row.prompt)
        self.assertIsNone(row.response)
        self.assertEqual((row.prompt_tokens, row.status), (3, AIRequestLog.Status.ERROR))
