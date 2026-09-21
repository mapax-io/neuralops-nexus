"""
Tests for intelligence/oauth_client.py -- run with:
    python manage.py test intelligence

Only the two functions that make real HTTP calls (OAuth2Client.fetch_token,
OAuth2Client.refresh_token) are mocked. Everything else -- state signing,
URL building, the storage logic in _store_token -- runs for real, so these
tests prove the actual code, not a simulation of it.
"""
from unittest.mock import patch

from django.core import signing
from django.test import TestCase

from chat.tests import MentionRightFixture

from intelligence import oauth_client
from nucleus.models import Company, MCPServer


class ClientOAuthTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Test Co", slug="test-co")
        self.server = MCPServer.objects.create(
            company=self.company,
            name="Fake Provider",
            transport=MCPServer.Transport.HTTP,
            url="http://fake-provider.example/mcp",   # satisfies the http transport CheckConstraint
            auth_type=MCPServer.AuthType.OAUTH2,
            oauth_config={
                "authorize_endpoint": "https://fake-provider.example/oauth/authorize",
                "token_endpoint": "https://fake-provider.example/oauth/token",
                "client_id": "test-client-id",
                "scopes": ["read", "write"],
                "token_env_var": "FAKE_PROVIDER_TOKEN",
            },
        )
        self.server.set_secrets({"client_secret": "test-client-secret"})
        self.server.save()

    # ── build_authorize_url ──────────────────────────────────────────────

    def test_build_authorize_url_contains_expected_params(self):
        url = oauth_client.build_authorize_url(self.server, frontend_origin="http://localhost:3000")
        self.assertIn("https://fake-provider.example/oauth/authorize", url)
        self.assertIn("client_id=test-client-id", url)
        self.assertIn("response_type=code", url)
        self.assertIn("state=", url)

    def test_build_authorize_url_state_round_trips(self):
        """The state embedded in the URL must decode back to server_id + frontend_origin --
        this is the entire CSRF/session-less-state mechanism, so it's worth proving directly."""
        url = oauth_client.build_authorize_url(self.server, frontend_origin="http://localhost:3000")
        state = url.split("state=")[1].split("&")[0]
        from urllib.parse import unquote
        decoded = signing.loads(unquote(state), salt=oauth_client._SIGNING_SALT)
        self.assertEqual(decoded["server_id"], str(self.server.id))
        self.assertEqual(decoded["frontend_origin"], "http://localhost:3000")

    # ── complete_callback ────────────────────────────────────────────────

    def _valid_state(self, frontend_origin="http://localhost:3000"):
        return signing.dumps(
            {"server_id": str(self.server.id), "frontend_origin": frontend_origin},
            salt=oauth_client._SIGNING_SALT,
        )

    @patch("intelligence.oauth_client.OAuth2Client.fetch_token")
    def test_complete_callback_stores_token(self, mock_fetch):
        mock_fetch.return_value = {
            "access_token": "fake-access-token",
            "refresh_token": "fake-refresh-token",
            "expires_in": 3600,
        }
        result = oauth_client.complete_callback(code="fake-code", state=self._valid_state())

        self.assertEqual(result["server_id"], str(self.server.id))
        self.assertEqual(result["frontend_origin"], "http://localhost:3000")

        self.server.refresh_from_db()
        secrets = self.server.get_secrets()
        self.assertEqual(secrets["FAKE_PROVIDER_TOKEN"], "fake-access-token")
        self.assertEqual(secrets["refresh_token"], "fake-refresh-token")
        self.assertIn("expires_at", self.server.oauth_config)

    def test_complete_callback_rejects_bad_state(self):
        with self.assertRaises(signing.BadSignature):
            oauth_client.complete_callback(code="fake-code", state="garbage-not-signed")

    def test_complete_callback_rejects_unknown_server(self):
        fake_state = signing.dumps(
            {"server_id": "00000000-0000-0000-0000-000000000000", "frontend_origin": "http://x"},
            salt=oauth_client._SIGNING_SALT,
        )
        with self.assertRaises(ValueError):
            oauth_client.complete_callback(code="fake-code", state=fake_state)

    # ── refresh_if_needed ────────────────────────────────────────────────

    def test_refresh_if_needed_true_for_non_oauth2_server(self):
        static_server = MCPServer.objects.create(
            company=self.company, name="Static", transport=MCPServer.Transport.HTTP,
            url="http://x.example/mcp", auth_type=MCPServer.AuthType.STATIC_SECRETS,
        )
        with patch("intelligence.oauth_client.OAuth2Client.refresh_token") as mock_refresh:
            self.assertTrue(oauth_client.refresh_if_needed(static_server))
            mock_refresh.assert_not_called()   # must not even try -- proves the early-return works

    def test_refresh_if_needed_false_when_never_connected(self):
        # no refresh_token in secrets at all
        self.assertFalse(oauth_client.refresh_if_needed(self.server))

    def test_refresh_if_needed_true_when_still_valid_skips_network(self):
        from django.utils import timezone
        from datetime import timedelta

        self.server.set_secrets({"refresh_token": "still-good", "client_secret": "test-client-secret"})
        self.server.oauth_config["expires_at"] = (timezone.now() + timedelta(hours=1)).isoformat()
        self.server.save()

        with patch("intelligence.oauth_client.OAuth2Client.refresh_token") as mock_refresh:
            self.assertTrue(oauth_client.refresh_if_needed(self.server))
            mock_refresh.assert_not_called()   # proves the 60s-buffer check actually skips the call

    @patch("intelligence.oauth_client.OAuth2Client.refresh_token")
    def test_refresh_if_needed_refreshes_when_expired(self, mock_refresh):
        from django.utils import timezone
        from datetime import timedelta

        self.server.set_secrets({"refresh_token": "old-refresh", "client_secret": "test-client-secret"})
        self.server.oauth_config["expires_at"] = (timezone.now() - timedelta(seconds=1)).isoformat()
        self.server.save()

        mock_refresh.return_value = {"access_token": "new-access-token", "expires_in": 3600}
        self.assertTrue(oauth_client.refresh_if_needed(self.server))

        self.server.refresh_from_db()
        self.assertEqual(self.server.get_secrets()["FAKE_PROVIDER_TOKEN"], "new-access-token")
        self.assertEqual(self.server.get_secrets()["refresh_token"], "old-refresh")  # preserved, provider omitted it

    @patch("intelligence.oauth_client.OAuth2Client.refresh_token", side_effect=Exception("invalid_grant"))
    def test_refresh_if_needed_false_when_provider_rejects(self, mock_refresh):
        from django.utils import timezone
        from datetime import timedelta

        self.server.set_secrets({"refresh_token": "dead-refresh-token"})
        self.server.oauth_config["expires_at"] = (timezone.now() - timedelta(seconds=1)).isoformat()
        self.server.save()

        self.assertFalse(oauth_client.refresh_if_needed(self.server))

    # ── _store_token ─────────────────────────────────────────────────────

    def test_store_token_preserves_refresh_token_when_response_omits_it(self):
        oauth_client._store_token(self.server, {"access_token": "t1", "refresh_token": "r1", "expires_in": 3600})
        oauth_client._store_token(self.server, {"access_token": "t2"})  # no refresh_token this time
        secrets = self.server.get_secrets()
        self.assertEqual(secrets["FAKE_PROVIDER_TOKEN"], "t2")
        self.assertEqual(secrets["refresh_token"], "r1")   # unchanged from the first call

class UtilityModelTests(MentionRightFixture):
    """
    W17: one model config per server is the utility model -- the model the
    server's own small jobs run on (recall passes, runbook conditions, titles)
    so a persona's model is not spent on them.
    """

    def setUp(self):
        super().setUp()
        from nucleus.models import ModelConfig
        self.small = ModelConfig.objects.create(
            company=self.company, name="Small", provider="openai", model_id="gpt-4o-mini", context_window=128000,
        )

    def test_owner_sets_and_clears_the_utility_model_and_the_list_marks_it(self):
        r = self.call("post", f"/api/v1/model-configs/{self.small.id}/utility/", self.owner)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(r.json()["is_utility"])
        rows = {m["id"]: m["is_utility"] for m in self.call("get", "/api/v1/model-configs/", self.owner).json()}
        self.assertEqual(rows[str(self.small.id)], True)
        self.assertEqual(rows[str(self.model_config.id)], False)
        self.assertEqual(self.call("get", "/api/v1/ai-config/", self.owner).json()["utility_model_id"], str(self.small.id))
        r = self.call("delete", f"/api/v1/model-configs/{self.small.id}/utility/", self.owner)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertFalse(r.json()["is_utility"])
        self.assertIsNone(self.call("get", "/api/v1/ai-config/", self.owner).json()["utility_model_id"])

    def test_only_a_model_config_editor_may_choose_it(self):
        r = self.call("post", f"/api/v1/model-configs/{self.small.id}/utility/", self.sara)
        self.assertEqual(r.status_code, 403, r.content)
        r = self.call("post", f"/api/v1/model-configs/{self.small.id}/utility/", self.owner)
        self.assertEqual(r.status_code, 200, r.content)
        r = self.call("delete", f"/api/v1/model-configs/{self.small.id}/utility/", self.sara)
        self.assertEqual(r.status_code, 403, r.content)

    def test_an_unknown_or_deleted_config_cannot_be_the_utility_model(self):
        r = self.call("post", "/api/v1/model-configs/00000000-0000-0000-0000-000000000000/utility/", self.owner)
        self.assertEqual(r.status_code, 404, r.content)
        self.small.soft_delete()
        r = self.call("post", f"/api/v1/model-configs/{self.small.id}/utility/", self.owner)
        self.assertEqual(r.status_code, 404, r.content)

    def test_deleting_the_utility_model_config_clears_the_pointer(self):
        from intelligence.services import delete_model_config, get_ai_config, set_utility_model
        set_utility_model(self.company, self.owner, str(self.small.id))
        self.assertTrue(delete_model_config(self.company, str(self.small.id)))
        self.assertIsNone(get_ai_config(self.company).utility_model)

    def test_the_persona_payload_carries_the_utility_model_with_its_key(self):
        import os
        from django.test import Client
        from intelligence.services import set_utility_model
        from nucleus.models import Prompt
        Prompt.objects.get_or_create(persona=self.persona_sara, defaults={"company": self.company, "system_prompt": "You are Sara.", "output_type": "text"})
        def payload():
            with patch.dict(os.environ, {"INTERNAL_API_KEY": "k"}):
                r = Client().get(f"/api/v1/internal/personas/{self.persona_sara.id}/", HTTP_X_INTERNAL_API_KEY="k")
            self.assertEqual(r.status_code, 200, r.content)
            return r.json()
        self.assertIsNone(payload()["utility_model"])
        set_utility_model(self.company, self.owner, str(self.small.id))
        u = payload()["utility_model"]
        self.assertEqual((u["id"], u["model_id"], u["qualified_id"]), (str(self.small.id), "gpt-4o-mini", "openai:gpt-4o-mini"))
        self.small.soft_delete()
        self.assertIsNone(payload()["utility_model"])  # a retired config is never handed out

    def test_the_ai_config_update_needs_the_same_right(self):
        body = {"embedding_provider": "fastembed", "embedding_model": "x", "embedding_base_url": "", "default_llm_model": "openai:gpt-4o-mini"}
        self.assertEqual(self.call("put", "/api/v1/ai-config/", self.sara, body).status_code, 403)
        self.assertEqual(self.call("put", "/api/v1/ai-config/", self.owner, body).status_code, 200)


class PersonaGateTests(MentionRightFixture):
    """`acts_after_approval` -- the persona proposes before acting -- round-trips."""

    def test_the_gate_is_off_by_default_and_patches_through(self):
        from intelligence.api import _persona_out
        from intelligence.services import patch_persona
        self.assertFalse(_persona_out(self.persona_sara).acts_after_approval)
        patch_persona(self.company, str(self.persona_sara.id), {"acts_after_approval": True})
        self.persona_sara.refresh_from_db()
        self.assertTrue(self.persona_sara.acts_after_approval)
        self.assertTrue(_persona_out(self.persona_sara).acts_after_approval)


class ToolLevelsTests(MentionRightFixture):
    """`tool_levels` -- Auto / Ask / Off per capability or tool -- round-trips and is validated."""

    def test_levels_are_empty_by_default_patch_through_and_reach_the_worker(self):
        from intelligence.api import _persona_out
        from intelligence.services import patch_persona
        from internal.api import get_persona_internal
        self.assertEqual(_persona_out(self.persona_sara).tool_levels, {})
        patch_persona(self.company, str(self.persona_sara.id), {"tool_levels": {"shell": "off", "filesystem/write_file": "ask", "mcp:abc": "auto"}})
        self.persona_sara.refresh_from_db()
        self.assertEqual(_persona_out(self.persona_sara).tool_levels, {"shell": "off", "filesystem/write_file": "ask", "mcp:abc": "auto"})
        from nucleus.models import Prompt
        Prompt.objects.create(company=self.company, persona=self.persona_sara, system_prompt="You are Sara.")
        payload = get_persona_internal(None, str(self.persona_sara.id)).model_dump()
        self.assertEqual(payload["tool_levels"], {"shell": "off", "filesystem/write_file": "ask", "mcp:abc": "auto"})

    def test_a_level_that_is_not_auto_ask_or_off_is_refused(self):
        from intelligence.services import patch_persona
        for bad in ({"shell": "sometimes"}, {"": "auto"}, {"shell": 1}):
            with self.assertRaises(ValueError):
                patch_persona(self.company, str(self.persona_sara.id), {"tool_levels": bad})
        self.persona_sara.refresh_from_db()
        self.assertEqual(self.persona_sara.tool_levels, {})


class RoutineTests(MentionRightFixture):
    """W4: team-shared methods invoked with `/` -- four built-ins per project, CRUD under routine.manage."""

    BUILTINS = {"pr-description", "incident-summary", "weekly-digest", "meeting-notes"}

    def routines(self, project):
        from nucleus.models import Routine
        return Routine.objects.filter(project=project, is_active=True)

    def test_seeding_creates_the_four_built_ins_once(self):
        from intelligence.services import seed_builtin_routines
        seed_builtin_routines(self.p1)
        seed_builtin_routines(self.p1)
        rows = self.routines(self.p1)
        self.assertEqual({r.name for r in rows}, self.BUILTINS)
        self.assertTrue(all(r.is_builtin and r.instructions and r.title and r.purpose for r in rows))
        self.assertEqual(self.routines(self.p2).count(), 0)

    def test_a_new_project_gets_its_built_ins(self):
        r = self.call("post", "/api/v1/projects/", self.owner, {"name": "Delta"})
        self.assertEqual(r.status_code, 200, r.content)
        from nucleus.models import Project
        delta = Project.objects.get(id=r.json()["id"])
        self.assertEqual({x.name for x in self.routines(delta)}, self.BUILTINS)

    def test_create_needs_routine_manage_validates_the_name_and_round_trips(self):
        path = f"/api/v1/projects/{self.p1.id}/routines/"
        body = {"name": "release-notes", "title": "Release notes", "purpose": "Draft release notes from merged PRs.", "instructions": "List every merged PR…", "allowed_capabilities": ["filesystem", "mcp:abc"]}
        self.assertEqual(self.call("post", path, self.sara, body).status_code, 403)   # a member uses routines, admins define them
        r = self.call("post", path, self.owner, body)
        self.assertEqual(r.status_code, 200, r.content)
        out = r.json()
        self.assertEqual((out["name"], out["is_builtin"], out["allowed_capabilities"], out["model"]), ("release-notes", False, ["filesystem", "mcp:abc"], None))
        self.assertEqual(self.call("post", path, self.owner, body).status_code, 400)  # the name is taken here
        for bad in ({**body, "name": "Release Notes"}, {**body, "name": ""}, {**body, "name": "x" * 41}, {**body, "instructions": "x" * 8001}, {**body, "allowed_capabilities": ["laser"]}):
            self.assertEqual(self.call("post", path, self.owner, bad).status_code, 400, bad.get("name"))

    def test_list_needs_only_to_read_the_project_and_shows_built_ins_and_own(self):
        from intelligence.services import seed_builtin_routines
        seed_builtin_routines(self.p1)
        path = f"/api/v1/projects/{self.p1.id}/routines/"
        r = self.call("get", path, self.sara)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual({x["name"] for x in r.json()}, self.BUILTINS)

    def test_patch_and_delete_a_built_in_is_editable_but_stays(self):
        from intelligence.services import seed_builtin_routines
        digest = next(x for x in seed_builtin_routines(self.p1) if x.name == "weekly-digest")
        base = f"/api/v1/projects/{self.p1.id}/routines/"
        r = self.call("patch", f"{base}{digest.id}/", self.owner, {"title": "Weekly digest (ops)", "model_config_id": str(self.model_config.id)})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual((r.json()["title"], r.json()["model"]["id"]), ("Weekly digest (ops)", str(self.model_config.id)))
        self.assertEqual(self.call("patch", f"{base}{digest.id}/", self.owner, {"clear_model": True}).json()["model"], None)
        self.assertEqual(self.call("delete", f"{base}{digest.id}/", self.owner).status_code, 409)
        own = self.call("post", base, self.owner, {"name": "mine", "title": "Mine", "purpose": "", "instructions": "do"}).json()
        self.assertEqual(self.call("delete", f"{base}{own['id']}/", self.sara).status_code, 403)
        self.assertEqual(self.call("delete", f"{base}{own['id']}/", self.owner).status_code, 204)
        self.assertNotIn("mine", {x["name"] for x in self.call("get", base, self.owner).json()})

    def test_the_worker_reads_a_routine_with_its_model_and_key(self):
        from intelligence.services import create_routine
        from internal.api import get_routine_internal
        routine = create_routine(self.company, self.p1, self.owner, {"name": "keyed", "title": "Keyed", "purpose": "", "instructions": "Use the small model.", "model_config": self.model_config})
        payload = get_routine_internal(None, str(routine.id)).model_dump()
        self.assertEqual((payload["name"], payload["instructions"], payload["allowed_capabilities"]), ("keyed", "Use the small model.", None))
        self.assertEqual(payload["model"]["id"], str(self.model_config.id))
        self.assertIn("api_key", payload["model"])


# ── W7 Model fallbacks ───────────────────────────────────────────────────────
class FallbackModelTests(MentionRightFixture):
    """A persona names up to three fallback models, in order; the worker gets them with their keys."""

    def setUp(self):
        super().setUp()
        from nucleus.models import ModelConfig
        self.small = ModelConfig.objects.create(company=self.company, name="Small", provider="openai", model_id="gpt-4o-mini")
        self.small.set_api_key("k-small")
        self.small.save(update_fields=["api_key_encrypted"])
        self.tiny = ModelConfig.objects.create(company=self.company, name="Tiny", provider="anthropic", model_id="claude-haiku-4-5-20251001")
        self.spare = ModelConfig.objects.create(company=self.company, name="Spare", provider="openai", model_id="gpt-4.1-nano")
        self.elsewhere = ModelConfig.objects.create(company=self.company, name="Elsewhere", provider="openai", model_id="o3")
        for m in (self.small, self.tiny, self.spare):
            m.projects.add(self.p1)

    def names(self, persona):
        from intelligence.api import _persona_out
        return [m.name for m in _persona_out(persona).fallback_models]

    def test_fallbacks_round_trip_in_order_reorder_and_clear(self):
        from intelligence.services import patch_persona
        self.assertEqual(self.names(self.persona_sara), [])
        patch_persona(self.company, str(self.persona_sara.id), {"fallback_model_config_ids": [str(self.small.id), str(self.tiny.id)]})
        self.assertEqual(self.names(self.persona_sara), ["Small", "Tiny"])
        patch_persona(self.company, str(self.persona_sara.id), {"fallback_model_config_ids": [str(self.tiny.id), str(self.small.id)]})
        self.assertEqual(self.names(self.persona_sara), ["Tiny", "Small"])
        patch_persona(self.company, str(self.persona_sara.id), {"name": "Sara"})  # not sent: untouched
        self.assertEqual(self.names(self.persona_sara), ["Tiny", "Small"])
        patch_persona(self.company, str(self.persona_sara.id), {"fallback_model_config_ids": []})
        self.assertEqual(self.names(self.persona_sara), [])

    def test_a_persona_is_created_with_its_fallbacks_over_the_api(self):
        body = {"name": "Nova", "project_id": str(self.p1.id), "model_config_id": str(self.model_config.id),
                "fallback_model_config_ids": [str(self.small.id), str(self.small.id), str(self.tiny.id)],  # a repeat collapses
                "prompt": {"system_prompt": "You are Nova."}}
        r = self.call("post", "/api/v1/personas/", self.owner, body)
        self.assertEqual(r.status_code, 201 if r.status_code == 201 else 200, r.content)
        self.assertEqual([m["name"] for m in r.json()["fallback_models"]], ["Small", "Tiny"])
        r = self.call("patch", f"/api/v1/personas/{r.json()['id']}/", self.owner, {"fallback_model_config_ids": []})
        self.assertEqual(r.json()["fallback_models"], [])

    def test_the_wiring_rules_apply_to_fallbacks(self):
        from intelligence.services import patch_persona
        pid = str(self.persona_sara.id)
        with self.assertRaisesRegex(ValueError, "three"):
            patch_persona(self.company, pid, {"fallback_model_config_ids": [str(self.small.id), str(self.tiny.id), str(self.spare.id), str(self.elsewhere.id)]})
        with self.assertRaisesRegex(ValueError, "different model from the primary"):
            patch_persona(self.company, pid, {"fallback_model_config_ids": [str(self.model_config.id)]})
        with self.assertRaisesRegex(ValueError, "not attached to this project"):
            patch_persona(self.company, pid, {"fallback_model_config_ids": [str(self.elsewhere.id)]})
        with self.assertRaisesRegex(ValueError, "not found"):
            patch_persona(self.company, pid, {"fallback_model_config_ids": ["00000000-0000-0000-0000-000000000000"]})
        # A primary swapped onto a current fallback is refused too.
        patch_persona(self.company, pid, {"fallback_model_config_ids": [str(self.small.id)]})
        with self.assertRaisesRegex(ValueError, "different model from the primary"):
            patch_persona(self.company, pid, {"model_config_id": str(self.small.id)})

    def test_a_model_in_use_as_a_fallback_cannot_be_deleted_or_detached(self):
        from intelligence.services import delete_model_config, detach_model_config_from_project, patch_persona
        patch_persona(self.company, str(self.persona_sara.id), {"fallback_model_config_ids": [str(self.small.id)]})
        with self.assertRaisesRegex(ValueError, "Sara"):
            delete_model_config(self.company, str(self.small.id))
        with self.assertRaisesRegex(ValueError, "Sara"):
            detach_model_config_from_project(self.company, str(self.small.id), str(self.p1.id))
        self.assertTrue(delete_model_config(self.company, str(self.spare.id)))  # unused: fine

    def test_the_worker_payload_carries_the_fallbacks_with_their_keys_and_skips_a_retired_one(self):
        from intelligence.services import patch_persona
        from internal.api import get_persona_internal
        from nucleus.models import Prompt
        Prompt.objects.create(company=self.company, persona=self.persona_sara, system_prompt="You are Sara.")
        patch_persona(self.company, str(self.persona_sara.id), {"fallback_model_config_ids": [str(self.small.id), str(self.tiny.id)]})
        payload = get_persona_internal(None, str(self.persona_sara.id)).model_dump()
        self.assertEqual([(m["name"], m["model_id"], m["api_key"]) for m in payload["fallback_models"]],
                         [("Small", "gpt-4o-mini", "k-small"), ("Tiny", "claude-haiku-4-5-20251001", None)])
        self.small.soft_delete()
        payload = get_persona_internal(None, str(self.persona_sara.id)).model_dump()
        self.assertEqual([m["name"] for m in payload["fallback_models"]], ["Tiny"])


# ── Model check on register / edit ──────────────────────────────────────────
class ModelCheckTests(MentionRightFixture):
    """The dialogs verify a model with the worker before saving; the answer is a reason the reader can act on."""

    def check(self, user, body, worker=None, side_effect=None):
        from unittest.mock import MagicMock, patch
        response = MagicMock(status_code=200)
        response.json.return_value = worker or {"ok": True, "latency_ms": 321}
        response.raise_for_status.return_value = None
        with patch("intelligence.services.httpx.post", return_value=response, side_effect=side_effect) as post:
            with self.settings(NEXUS_AI_URL="http://worker.test", INTERNAL_API_KEY="k"):
                r = self.call("post", "/api/v1/model-configs/check/", user, body)
        return r, post

    def test_the_right_is_checked_and_a_passing_model_answers_ok_with_its_latency(self):
        body = {"provider": "openai", "model_id": "gpt-4o-mini", "api_key": "sk-new"}
        r, post = self.check(self.sara, body)
        self.assertEqual(r.status_code, 403, r.content)
        r, post = self.check(self.owner, body)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json(), {"ok": True, "reason": None, "latency_ms": 321})
        sent = post.call_args.kwargs["json"]
        self.assertEqual(sent, {"provider": "openai", "model_id": "gpt-4o-mini", "api_key": "sk-new", "api_base": None})
        self.assertEqual(post.call_args.kwargs["headers"]["X-Internal-Key"], "k")

    def test_a_failing_model_gets_the_categorised_reason_never_the_raw_text(self):
        body = {"provider": "openai", "model_id": "gpt-4o-mini", "api_key": "sk-bad"}
        r, _ = self.check(self.owner, body, worker={"ok": False, "error_code": "model_failure", "status_code": 401,
                                                    "error": "status_code: 401, body: Incorrect API key provided: sk-bad***"})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertFalse(r.json()["ok"])
        self.assertEqual(r.json()["reason"], "The model provider rejected this model's API key.")  # no pointer to the page the reader is on
        self.assertNotIn("sk-bad", r.json()["reason"])
        r, _ = self.check(self.owner, body, worker={"ok": False, "error_code": "unsupported_provider", "error": "provider 'google' is not supported"})
        self.assertIn("cannot run openai models", r.json()["reason"])
        r, _ = self.check(self.owner, body, worker={"ok": False, "error_code": "timeout", "error": "the model did not answer within 20s (timed out)"})
        self.assertIn("timed out", r.json()["reason"])
        # DeepSeek's unknown-model wording, and a text no category knows.
        r, _ = self.check(self.owner, body, worker={"ok": False, "error_code": "error", "status_code": 400, "error": "status_code: 400, body: {'error': {'message': 'Model Not Exist'}}"})
        self.assertIn("does not know this model id", r.json()["reason"])
        r, _ = self.check(self.owner, body, worker={"ok": False, "error_code": "error", "status_code": 400, "error": "body: {'message': 'The supported API model names are deepseek-flash, deepseek-v4-pro, but you passed deepseek-x.'}"})
        self.assertIn("does not know this model id", r.json()["reason"])
        r, _ = self.check(self.owner, body, worker={"ok": False, "error_code": "error", "status_code": 418, "error": "teapot"})
        self.assertEqual(r.json()["reason"], "The model provider did not accept this model with this key (HTTP 418).")

    def test_an_edit_without_a_new_key_checks_with_the_stored_one(self):
        self.model_config.set_api_key("sk-stored")
        self.model_config.save(update_fields=["api_key_encrypted"])
        body = {"provider": "openai", "model_id": "gpt-4.1", "config_id": str(self.model_config.id)}
        r, post = self.check(self.owner, body)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(post.call_args.kwargs["json"]["api_key"], "sk-stored")
        body["api_key"] = "sk-rotated"  # a new key wins over the stored one
        r, post = self.check(self.owner, body)
        self.assertEqual(post.call_args.kwargs["json"]["api_key"], "sk-rotated")

    def test_bad_input_and_a_missing_worker_are_told_apart(self):
        r, _ = self.check(self.owner, {"provider": "openai", "model_id": "openai/gpt-4o-mini", "api_key": "k"})
        self.assertEqual(r.status_code, 400, r.content)
        r, _ = self.check(self.owner, {"provider": "nope", "model_id": "x", "api_key": "k"})
        self.assertEqual(r.status_code, 400, r.content)
        import httpx
        r, _ = self.check(self.owner, {"provider": "openai", "model_id": "gpt-4o-mini", "api_key": "k"}, side_effect=httpx.ConnectError("refused"))
        self.assertEqual(r.status_code, 502, r.content)
        with self.settings(NEXUS_AI_URL=""):
            r = self.call("post", "/api/v1/model-configs/check/", self.owner, {"provider": "openai", "model_id": "gpt-4o-mini", "api_key": "k"})
        self.assertEqual(r.status_code, 503, r.content)


# ── W5 Recall ────────────────────────────────────────────────────────────────
class RecallTests(MentionRightFixture):
    """What personas record about a project: stored once, attributed, embedded by the worker, edited under recall.manage."""

    def setUp(self):
        super().setUp()
        from unittest.mock import MagicMock, patch
        self.embed_calls = []
        self.delete_calls = []
        def fake_post(url, json=None, headers=None, timeout=None):
            self.embed_calls.append(json)
            response = MagicMock(status_code=200)
            response.raise_for_status.return_value = None
            return response
        def fake_delete(url, params=None, headers=None, timeout=None):
            self.delete_calls.append((url, params))
            return MagicMock(status_code=200)
        for target, value in (("intelligence.recall.httpx.post", fake_post), ("intelligence.recall.httpx.delete", fake_delete)):
            patcher = patch(target, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        # Inline here so the calls can be asserted; in production they run off the request.
        self.settings_patch = self.settings(NEXUS_AI_URL="http://worker.test", INTERNAL_API_KEY="k", RECALL_EMBED_INLINE=True)
        self.settings_patch.enable()
        self.addCleanup(self.settings_patch.disable)
        from nucleus.models import ChatMessage
        self.msg = ChatMessage.objects.create(company=self.company, project=self.p1, topic=self.t1, sender=self.owner, content="let's use Postgres", sequence=1)

    def record(self, entries, **kw):
        from intelligence.recall import record_recall
        return record_recall(self.p1, entries, **kw)

    def test_entries_are_stored_once_attributed_and_embedded(self):
        out = self.record([
            {"kind": "decision", "text": "We use Postgres for the warehouse."},
            {"kind": "fact", "text": "  The API   lives in nucleus.  "},
            {"kind": "Decision", "text": "we use postgres for the warehouse"},  # the same thing, said again
        ], persona=self.persona_sara, message=self.msg)
        self.assertEqual((len(out["created"]), out["skipped"]), (2, 1))
        first = out["created"][0]
        self.assertEqual((first.kind, first.text, first.normalized), ("decision", "We use Postgres for the warehouse.", "we use postgres for the warehouse"))
        self.assertEqual((first.author_persona, first.source_message, first.source_topic), (self.persona_sara, self.msg, self.t1))
        self.assertEqual(out["created"][1].text, "The API lives in nucleus.")
        self.assertEqual([c["text"] for c in self.embed_calls], ["We use Postgres for the warehouse.", "The API lives in nucleus."])
        self.assertEqual(self.embed_calls[0]["collection_id"] if "collection_id" in self.embed_calls[0] else self.embed_calls[0]["project_id"], str(self.p1.id))
        self.assertEqual(self.embed_calls[0]["author_name"], "Sara")
        # Recorded again later: skipped, not duplicated.
        out = self.record([{"kind": "decision", "text": "We use Postgres for the warehouse!"}], persona=self.persona_sara)
        self.assertEqual((len(out["created"]), out["skipped"]), (0, 1))

    def test_invalid_entries_are_refused_and_the_caps_hold(self):
        for bad in ({"kind": "wish", "text": "x"}, {"kind": "fact", "text": "   "}, {"kind": "fact", "text": "x" * 501}):
            with self.assertRaises(ValueError):
                self.record([bad])
        out = self.record([{"kind": "fact", "text": f"fact number {i}"} for i in range(7)])
        self.assertEqual((len(out["created"]), out["skipped"]), (5, 2))
        from unittest.mock import patch
        with patch("intelligence.recall.RECALL_PER_PROJECT_MAX", 6):
            out = self.record([{"kind": "fact", "text": "one more"}, {"kind": "fact", "text": "and another"}])
        self.assertEqual((len(out["created"]), out["skipped"]), (1, 1))

    def test_the_worker_writes_through_the_internal_route(self):
        from django.test import Client
        import os
        body = {"project_id": str(self.p1.id), "persona_id": str(self.persona_sara.id), "message_id": str(self.msg.id),
                "entries": [{"kind": "preference", "text": "Answer in bullet points."}, {"kind": "preference", "text": "answer in bullet points"}]}
        with patch_env():
            r = Client().post("/api/v1/internal/recall/", data=body, content_type="application/json", HTTP_X_INTERNAL_API_KEY="k")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json(), {"created": 1, "skipped": 1})
        entry = self.p1.recallentry_items.get(is_active=True)
        self.assertEqual((entry.author_persona, entry.source_topic), (self.persona_sara, self.t1))
        with patch_env():
            r = Client().post("/api/v1/internal/recall/", data={**body, "persona_id": str(self.persona_bob.id), "project_id": str(self.p2.id)}, content_type="application/json", HTTP_X_INTERNAL_API_KEY="k")
        self.assertEqual(r.status_code, 404, r.content)  # Bob is not in Beta

    def test_reading_needs_the_project_editing_needs_the_right_and_the_vector_follows(self):
        entry = self.record([{"kind": "fact", "text": "Deploys go out on Tuesdays."}], persona=self.persona_sara, message=self.msg)["created"][0]
        r = self.call("get", f"/api/v1/projects/{self.p1.id}/recall/", self.sara)
        self.assertEqual(r.status_code, 200, r.content)
        row = r.json()[0]
        self.assertEqual((row["kind"], row["text"], row["author_name"], row["source"]["topic_title"], row["source"]["message_id"]), ("fact", "Deploys go out on Tuesdays.", "Sara", "t1", str(self.msg.id)))
        self.assertEqual(self.call("get", f"/api/v1/projects/{self.p1.id}/recall/?kind=decision", self.sara).json(), [])
        self.assertEqual(len(self.call("get", f"/api/v1/projects/{self.p1.id}/recall/?q=tuesday", self.sara).json()), 1)
        self.assertEqual(self.call("get", f"/api/v1/projects/{self.p1.id}/recall/", self.vera).status_code, 200)  # a viewer reads
        r = self.call("patch", f"/api/v1/projects/{self.p1.id}/recall/{entry.id}/", self.vera, {"text": "Deploys go out on Wednesdays."})
        self.assertEqual(r.status_code, 403, r.content)  # a viewer reads; curating what is recorded is recall.manage (Member tier)
        r = self.call("patch", f"/api/v1/projects/{self.p1.id}/recall/{entry.id}/", self.sara, {"text": "Deploys go out on Wednesdays.", "kind": "decision"})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual((r.json()["text"], r.json()["kind"]), ("Deploys go out on Wednesdays.", "decision"))
        self.assertEqual(self.embed_calls[-1]["text"], "Deploys go out on Wednesdays.")  # re-embedded
        self.record([{"kind": "fact", "text": "Standup is at ten."}])
        r = self.call("patch", f"/api/v1/projects/{self.p1.id}/recall/{entry.id}/", self.owner, {"text": "standup is at ten"})
        self.assertEqual(r.status_code, 400, r.content)  # already recorded
        self.assertEqual(self.call("delete", f"/api/v1/projects/{self.p1.id}/recall/{entry.id}/", self.vera).status_code, 403)
        self.assertEqual(self.call("delete", f"/api/v1/projects/{self.p1.id}/recall/{entry.id}/", self.sara).status_code, 204)
        self.assertEqual(self.delete_calls[-1][0], f"http://worker.test/api/v1/embed/recall/{entry.id}/")
        self.assertEqual(len(self.call("get", f"/api/v1/projects/{self.p1.id}/recall/", self.owner).json()), 1)
        # A removed entry can be recorded again.
        self.assertEqual(len(self.record([{"kind": "decision", "text": "Deploys go out on Wednesdays."}])["created"]), 1)

    def test_recall_enabled_round_trips_and_gates_the_source_the_worker_gets(self):
        from intelligence.api import _persona_out
        from intelligence.services import patch_persona
        from internal.api import get_persona_internal
        from chat.services import _build_context_sources
        from nucleus.models import Prompt
        self.assertTrue(_persona_out(self.persona_sara).recall_enabled)
        self.assertEqual([s["type"] for s in _build_context_sources(self.t1, self.company, self.persona_sara)], ["chat", "recall"])
        self.assertEqual(_build_context_sources(self.t1, self.company, self.persona_sara)[-1]["collection_id"], f"company_{self.company.id}_recall")
        patch_persona(self.company, str(self.persona_sara.id), {"recall_enabled": False})
        self.persona_sara.refresh_from_db()
        self.assertFalse(_persona_out(self.persona_sara).recall_enabled)
        self.assertEqual([s["type"] for s in _build_context_sources(self.t1, self.company, self.persona_sara)], ["chat"])
        Prompt.objects.create(company=self.company, persona=self.persona_sara, system_prompt="You are Sara.")
        self.assertFalse(get_persona_internal(None, str(self.persona_sara.id)).model_dump()["recall_enabled"])


def patch_env():
    import os
    from unittest.mock import patch
    return patch.dict(os.environ, {"INTERNAL_API_KEY": "k"})
