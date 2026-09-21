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

    def call(self, method, path, user, body=None):
        from django.test import Client
        with patch("authn.auth.verify_supabase_token", return_value={"email": user.email}):
            return getattr(Client(), method)(path, data=body, content_type="application/json", HTTP_AUTHORIZATION="Bearer t")

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
