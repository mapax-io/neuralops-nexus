"""
Step 3 — what the internal API now serves the engine
(docs/NUCLEUS-REVAMP.md Step 3; handoff changes 2 + 3 + 7 + 14.6).

history rows carry `status` (the engine drops non-COMPLETED rows), and the
persona payload carries the model seats (router resolved through the company
default), the supervisor checkbox and the tool-access/approval-scope flags.
"""
import os
from unittest.mock import patch

from django.test import Client

from chat.tests import MentionRightFixture
from nucleus.models import ChatMessage, CompanyAIConfig, ModelConfig, Prompt


class HistoryStatusTests(MentionRightFixture):
    def rows(self):
        with patch.dict(os.environ, {"INTERNAL_API_KEY": "k"}):
            r = Client().get(f"/api/v1/internal/topics/{self.t1.id}/history/", HTTP_X_INTERNAL_API_KEY="k")
        self.assertEqual(r.status_code, 200, r.content)
        return r.json()

    def test_history_rows_carry_status_and_output_type(self):
        """Change 2: the engine reads status to drop failed/cancelled rows from
        prompts; change 11.2: output_type resolves 'show it as a chart' follow-ups."""
        ChatMessage.objects.create(
            company=self.company, project=self.p1, topic=self.t1, sender=self.sara,
            content="draw it", sequence=1, status=ChatMessage.Status.COMPLETED, metadata={"role": "user"},
        )
        ChatMessage.objects.create(
            company=self.company, project=self.p1, topic=self.t1, sender=self.persona_sara.identity_user,
            content='{"type": "bar"}', sequence=2, status=ChatMessage.Status.COMPLETED,
            metadata={"persona_id": str(self.persona_sara.id), "persona_name": "Sara",
                      "output_type": "chart", "render_as": "chart"},
        )
        ChatMessage.objects.create(
            company=self.company, project=self.p1, topic=self.t1, sender=self.persona_sara.identity_user,
            content="", sequence=3, status=ChatMessage.Status.FAILED,
            metadata={"persona_id": str(self.persona_sara.id), "persona_name": "Sara"},
        )
        rows = self.rows()
        self.assertEqual([(r["status"], r["output_type"]) for r in rows], [
            ("completed", "text"),
            ("completed", "chart"),
            ("failed", "text"),
        ])


class PersonaSeatsTests(MentionRightFixture):
    """Changes 3 + 7 + 14.6: seats and flags ride PersonaInternal."""

    def setUp(self):
        super().setUp()
        Prompt.objects.get_or_create(
            persona=self.persona_sara,
            defaults={"company": self.company, "system_prompt": "You are Sara.", "output_type": "text"},
        )
        self.cheap = ModelConfig.objects.create(
            company=self.company, name="Cheap", provider="openai", model_id="gpt-cheap",
        )

    def payload(self):
        with patch.dict(os.environ, {"INTERNAL_API_KEY": "k"}):
            r = Client().get(f"/api/v1/internal/personas/{self.persona_sara.id}/", HTTP_X_INTERNAL_API_KEY="k")
        self.assertEqual(r.status_code, 200, r.content)
        return r.json()

    def test_defaults_are_the_safe_ones(self):
        """No seats, no flags set: router/deep null, delegation off, access all,
        scope topic — exactly what the engine treats as 'nothing special'."""
        p = self.payload()
        self.assertIsNone(p["router_model"])
        self.assertIsNone(p["deep_model"])
        self.assertFalse(p["delegation_enabled"])
        self.assertEqual((p["tool_access"], p["approval_scope"]), ("all", "topic"))

    def test_seats_and_flags_ride_the_persona(self):
        self.persona_sara.router_model = self.cheap
        self.persona_sara.deep_model = self.model_config
        self.persona_sara.delegation_enabled = True
        self.persona_sara.tool_access = "selected"
        self.persona_sara.approval_scope = "requester_only"
        self.persona_sara.save()
        p = self.payload()
        self.assertEqual(p["router_model"]["model_id"], "gpt-cheap")
        # Smart router: the deep FK alone (no bench rows — this test writes the
        # ORM directly) still serves as a one-item bench, and deep_model
        # mirrors its first entry for an older engine image.
        self.assertEqual(p["deep_model"]["model_id"], "gpt-test")
        self.assertEqual([m["model_id"] for m in p["deep_models"]], ["gpt-test"])
        self.assertTrue(p["delegation_enabled"])
        self.assertEqual((p["tool_access"], p["approval_scope"]), ("selected", "requester_only"))

    def test_the_project_default_fills_an_empty_router_seat(self):
        """Seats ruling (2026-10-19 23:43): the default router is a PROJECT
        setting, resolved INTO router_model before the persona is served. A
        persona's own seat wins; a default equal to the persona's STANDARD
        model is skipped (screening with the same model saves nothing); the
        dormant company-wide column is not read any more."""
        self.p1.default_router_model = self.cheap
        self.p1.save(update_fields=["default_router_model"])
        p = self.payload()
        self.assertEqual(p["router_model"]["model_id"], "gpt-cheap")
        # A persona's OWN seat beats the default.
        self.persona_sara.router_model = self.model_config
        self.persona_sara.save(update_fields=["router_model"])
        self.assertEqual(self.payload()["router_model"]["model_id"], "gpt-test")
        # A default equal to the persona's standard model is skipped.
        self.persona_sara.router_model = None
        self.persona_sara.save(update_fields=["router_model"])
        self.p1.default_router_model = self.persona_sara.model
        self.p1.save(update_fields=["default_router_model"])
        self.assertIsNone(self.payload()["router_model"])
        # The company-wide column is dormant: setting it fills nothing.
        self.p1.default_router_model = None
        self.p1.save(update_fields=["default_router_model"])
        CompanyAIConfig.objects.get_or_create(company=self.company, defaults={"default_router_model": self.cheap})
        self.assertIsNone(self.payload()["router_model"])
