"""
Step 1 — the money tables (docs/NUCLEUS-REVAMP.md §2.4, built 2026-10-14).

What is pinned here:
  pricing      — override beats catalog beats nothing; exact Decimal math on
                 the engine's token semantics (uncached / cache read / cache
                 writes at the input rate / output)
  internal API — POST /internal/usage/ stores one row per record, prices at
                 insert, refuses the wrong key, and pushes the topic's
                 running totals (usage_totals) marked price_estimated
  read API     — topic totals for anyone who can see the topic; the project
                 rollup needs usage.view_project; the company rollup needs
                 usage.view_company (owner's visibility ruling)
"""
import os
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import patch

from django.test import Client

from chat.tests import MentionRightFixture
from intelligence.pricing import price_record
from nucleus.models import ModelPrice, UsageRecord

CALLED_AT = datetime(2026, 10, 14, 12, 0, 0, tzinfo=timezone.utc)


class UsageFixture(MentionRightFixture):
    """The chat fixture (company, Alpha/c1/t1, owner + Sara the member +
    Vera the viewer, ModelConfig 'gpt-test') plus usage helpers."""

    def record(self, **over) -> dict:
        """One engine-shaped record, exactly as nexus-ai's _usage_payload
        sends it (cost/prices_used null — nucleus prices)."""
        base = {
            "company_id": str(self.company.id), "project_id": str(self.p1.id),
            "topic_id": str(self.t1.id), "persona_id": str(self.persona_sara.id),
            "user_id": "", "message_id": "msg-1", "job_id": "job-1",
            "kind": "chat_reply", "model_config_id": str(self.model_config.id),
            "provider": "openai", "model_id": "gpt-test", "role": "STANDARD",
            "provider_response_id": None, "source": None,
            "input_tokens": 1_750_000, "uncached_input_tokens": 1_000_000,
            "cache_read_tokens": 500_000, "cache_write_5m_tokens": 250_000,
            "cache_write_1h_tokens": 0, "output_tokens": 250_000,
            "reasoning_tokens": 0, "finish_reason": "stop", "estimated": False,
            "called_at": CALLED_AT.isoformat(),
            "cost": None, "prices_used": None,
        }
        base.update(over)
        return base

    def post_usage(self, records, key="k"):
        with patch.dict(os.environ, {"INTERNAL_API_KEY": "k"}):
            return Client().post(
                "/api/v1/internal/usage/", data={"records": records},
                content_type="application/json", HTTP_X_INTERNAL_API_KEY=key,
            )

    def catalog_price(self):
        return ModelPrice.objects.create(
            provider="openai", model_id="gpt-test",
            input_per_million=Decimal("1.00"), cached_per_million=Decimal("0.10"),
            output_per_million=Decimal("4.00"), source="litellm-catalog",
        )


class PricingTests(UsageFixture):
    """intelligence/pricing.py — the lookup order and the arithmetic."""

    def test_the_admin_override_beats_the_catalog(self):
        """Override typed on the ModelConfig row wins even when a catalog row
        exists; an untyped cached price defaults to the INPUT price.
        (400k uncached + 200k read + 100k writes) * 2.50 + 50k * 10.00 = 2.25"""
        self.catalog_price()
        self.model_config.price_input_per_million = Decimal("2.50")
        self.model_config.price_output_per_million = Decimal("10.00")
        self.model_config.save()
        money = price_record(self.record(
            uncached_input_tokens=400_000, cache_read_tokens=200_000,
            cache_write_5m_tokens=100_000, cache_write_1h_tokens=0,
            output_tokens=50_000))
        self.assertEqual(money["price_source"], "override")
        self.assertEqual(money["cost"], Decimal("2.25"))
        # compare as numbers — the 6-dp column returns "2.500000"
        self.assertEqual(Decimal(money["prices_used"]["cached_per_million"]), Decimal("2.50"))

    def test_the_catalog_prices_when_no_override_is_typed(self):
        """1M uncached * 1.00 + 500k read * 0.10 + 250k writes * 1.00 (input
        rate) + 250k out * 4.00 = 2.30 — exact Decimal, never float."""
        self.catalog_price()
        money = price_record(self.record())
        self.assertEqual(money["price_source"], "catalog")
        self.assertEqual(money["cost"], Decimal("2.30"))

    def test_a_compatible_endpoint_falls_back_to_the_bare_model_id(self):
        """openai_compatible serves a well-known model: no (provider, model)
        row matches, the bare model_id row still prices it."""
        self.catalog_price()
        money = price_record(self.record(provider="openai_compatible", model_config_id=""))
        self.assertEqual(money["price_source"], "catalog")
        self.assertIsNotNone(money["cost"])

    def test_no_price_known_means_cost_null_never_a_guess(self):
        money = price_record(self.record(provider="mystery", model_id="unknown-9", model_config_id=""))
        self.assertIsNone(money["cost"])
        self.assertEqual(money["price_source"], "")


class InternalUsageEndpointTests(UsageFixture):
    """POST /api/v1/internal/usage/ — the engine's batch lands as rows."""

    def test_the_wrong_key_is_refused(self):
        self.assertEqual(self.post_usage([self.record()], key="nope").status_code, 401)
        self.assertEqual(UsageRecord.objects.count(), 0)

    def test_a_batch_is_stored_priced_and_the_null_cost_is_ignored(self):
        """Two records (the reply + its router call) → two rows, each priced
        at insert from the catalog; the engine's cost:null validates and is
        discarded; the delegation-style message id fits as-is."""
        self.catalog_price()
        r = self.post_usage([
            self.record(),
            self.record(message_id="msg-1:cp0", kind="router", role="ROUTER",
                        uncached_input_tokens=10_000, cache_read_tokens=0,
                        cache_write_5m_tokens=0, output_tokens=1_000,
                        input_tokens=10_000),
        ])
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json(), {"ok": True, "saved": 2})
        reply = UsageRecord.objects.get(message_id="msg-1")
        self.assertEqual(reply.cost, Decimal("2.30"))
        self.assertEqual(reply.price_source, "catalog")
        self.assertEqual(reply.called_at, CALLED_AT)
        router_row = UsageRecord.objects.get(message_id="msg-1:cp0")
        # 10k * 1.00 + 1k * 4.00 = 0.014
        self.assertEqual(router_row.cost, Decimal("0.014"))

    def test_no_price_stores_the_tokens_with_cost_null(self):
        r = self.post_usage([self.record(provider="mystery", model_id="unknown-9", model_config_id="")])
        self.assertEqual(r.status_code, 201)
        row = UsageRecord.objects.get()
        self.assertIsNone(row.cost)
        self.assertEqual(row.input_tokens, 1_750_000)
        self.assertEqual(row.price_source, "")

    def test_the_topic_totals_go_out_live_and_say_estimated(self):
        """One insert → one usage_totals on the topic's channel: the summed
        tokens, the summed cost as a string, price_estimated true (owner's
        ruling — money is never presented as confirmed)."""
        self.catalog_price()
        with patch("chat.services.publish") as publish:
            self.post_usage([self.record()])
        [(channel, payload)] = [c.args for c in publish.call_args_list]
        self.assertIn(str(self.t1.id), channel)
        self.assertEqual(payload["type"], "usage_totals")
        self.assertEqual(payload["input_tokens"], 1_750_000)
        self.assertEqual(payload["output_tokens"], 250_000)
        self.assertEqual(payload["cost"], "2.30000000")
        self.assertEqual(payload["unpriced_rows"], 0)
        self.assertTrue(payload["price_estimated"])


class UsageReadApiTests(UsageFixture):
    """The three windows and their gates (owner's visibility ruling)."""

    def seed_rows(self):
        self.catalog_price()
        self.post_usage([
            self.record(),
            self.record(message_id="msg-2", persona_id=str(self.persona_bob.id),
                        uncached_input_tokens=100_000, cache_read_tokens=0,
                        cache_write_5m_tokens=0, input_tokens=100_000,
                        output_tokens=25_000),
        ])

    def topic_path(self):
        return f"/api/v1/projects/{self.p1.id}/channels/{self.c1.id}/topics/{self.t1.id}/usage/"

    def test_anyone_in_the_topic_sees_the_topic_totals(self):
        """Sara is a plain Member — no usage right — yet the topic she can
        read shows her what it cost, split per persona, labeled estimated."""
        self.seed_rows()
        r = self.call("get", self.topic_path(), self.sara)
        self.assertEqual(r.status_code, 200, r.content)
        body = r.json()
        self.assertEqual(body["input_tokens"], 1_850_000)
        self.assertEqual(body["rows"], 2)
        self.assertTrue(body["price_estimated"])
        self.assertEqual(body["note"], "Estimated — prices not confirmed.")
        self.assertEqual({p["persona_id"] for p in body["by_persona"]},
                         {str(self.persona_sara.id), str(self.persona_bob.id)})

    def test_the_project_rollup_needs_usage_view_project(self):
        self.seed_rows()
        self.assertEqual(self.call("get", f"/api/v1/projects/{self.p1.id}/usage/", self.sara).status_code, 403)
        r = self.call("get", f"/api/v1/projects/{self.p1.id}/usage/", self.owner)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(len(r.json()["by_persona"]), 2)
        self.assertEqual(r.json()["by_model"][0]["model_id"], "gpt-test")

    def test_the_company_rollup_needs_usage_view_company(self):
        self.seed_rows()
        self.assertEqual(self.call("get", "/api/v1/usage/company/", self.vera).status_code, 403)
        r = self.call("get", "/api/v1/usage/company/", self.owner)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["by_project"][0]["project_id"], str(self.p1.id))
        self.assertTrue(r.json()["price_estimated"])
