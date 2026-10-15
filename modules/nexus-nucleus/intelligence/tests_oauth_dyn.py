"""
Step 6 Part C -- the OAuth roads. Run with:
    python manage.py test intelligence

What these prove, over the real code (only httpx and the token exchange are
faked -- state signing, URL building, config storage all run for real):

  1. Dynamic client registration (the MCP standard): an oauth2 server row with
     NOTHING pasted gets discovered and registered on the Connect click.
  2. A provider without dynamic registration gets a clear, actionable refusal
     (502 through the API), never a crash.
  3. PKCE rides the authorize URL (code_challenge + S256) and the callback's
     exchange carries the matching code_verifier out of the signed state.
  4. redirect_mode "portal_relay" points the provider at the portal's one
     address, and the state carries server_url so the relay can bounce home.
"""
from unittest.mock import patch

from django.core import signing
from django.test import TestCase

from chat.tests import MentionRightFixture
from intelligence import oauth_client
from nucleus.models import Company, MCPServer, Project


class FakeResp:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.text = text or str(self._payload)

    def json(self):
        return self._payload


RESOURCE_META = {"authorization_servers": ["https://auth.modern.example"]}
AUTH_META = {
    "authorization_endpoint": "https://auth.modern.example/authorize",
    "token_endpoint": "https://auth.modern.example/token",
    "registration_endpoint": "https://auth.modern.example/register",
}


def _fake_get_factory(auth_meta=AUTH_META, resource=RESOURCE_META):
    def fake_get(url, **kwargs):
        if url.endswith("/.well-known/oauth-protected-resource"):
            return FakeResp(200, resource) if resource else FakeResp(404)
        if url.endswith("/.well-known/oauth-authorization-server"):
            return FakeResp(200, auth_meta) if auth_meta else FakeResp(404)
        return FakeResp(404)
    return fake_get


class DynamicRegistrationTests(TestCase):
    """ensure_client() -- discovery + self-registration, and its refusals."""

    def setUp(self):
        self.company = Company.objects.create(name="Test Co", slug="test-co")
        self.project = Project.objects.create(company=self.company, name="P", slug="p")
        self.server = MCPServer.objects.create(
            company=self.company, project=self.project, name="Modern MCP",
            transport=MCPServer.Transport.HTTP, url="https://modern.example/mcp",
            auth_type=MCPServer.AuthType.OAUTH2,
            oauth_config={"scopes": ["mcp.read"]},   # NOTHING pasted
        )

    def test_registration_fills_the_client_and_keeps_the_secret_out_of_config(self):
        def fake_post(url, json=None, timeout=None):
            self.assertEqual(url, AUTH_META["registration_endpoint"])
            # The registration body IS the contract: a public NeuralOps client.
            self.assertEqual(json["client_name"], "NeuralOps")
            self.assertEqual(json["token_endpoint_auth_method"], "none")
            self.assertEqual(json["grant_types"], ["authorization_code", "refresh_token"])
            self.assertTrue(json["redirect_uris"][0].endswith("/api/v1/mcp-servers/oauth/callback/"))
            return FakeResp(201, {"client_id": "dyn-client-123", "client_secret": "dyn-secret"})

        with patch("intelligence.oauth_client.httpx.get", _fake_get_factory()), \
             patch("intelligence.oauth_client.httpx.post", fake_post):
            ok, reason = oauth_client.ensure_client(self.server)
        self.assertEqual((ok, reason), (True, ""), reason)
        self.server.refresh_from_db()
        cfg = self.server.oauth_config
        self.assertEqual(cfg["client_id"], "dyn-client-123")
        self.assertEqual(cfg["authorize_endpoint"], AUTH_META["authorization_endpoint"])
        self.assertEqual(cfg["token_endpoint"], AUTH_META["token_endpoint"])
        self.assertNotIn("client_secret", cfg)  # secrets NEVER sit in plain config
        self.assertEqual(self.server.get_secrets().get("client_secret"), "dyn-secret")

    def test_a_fully_pasted_config_passes_through_without_a_single_request(self):
        self.server.oauth_config = {
            "client_id": "pasted", "authorize_endpoint": "https://a/x", "token_endpoint": "https://a/t",
        }
        self.server.save()
        with patch("intelligence.oauth_client.httpx.get") as get, \
             patch("intelligence.oauth_client.httpx.post") as post:
            ok, reason = oauth_client.ensure_client(self.server)
        self.assertEqual((ok, reason), (True, ""))
        get.assert_not_called()
        post.assert_not_called()

    def test_no_registration_endpoint_is_a_clear_refusal_not_a_crash(self):
        meta = {k: v for k, v in AUTH_META.items() if k != "registration_endpoint"}
        with patch("intelligence.oauth_client.httpx.get", _fake_get_factory(auth_meta=meta)), \
             patch("intelligence.oauth_client.httpx.post") as post:
            ok, reason = oauth_client.ensure_client(self.server)
        self.assertFalse(ok)
        self.assertIn("paste", reason)   # it tells the admin exactly what to do
        post.assert_not_called()

    def test_a_dead_or_metadata_less_server_answers_with_a_reason(self):
        with patch("intelligence.oauth_client.httpx.get", _fake_get_factory(auth_meta=None, resource=None)):
            ok, reason = oauth_client.ensure_client(self.server)
        self.assertFalse(ok)
        self.assertIn("discover", reason)


class OAuthRoadsApiTests(MentionRightFixture):
    """The roads end-to-end through GET /mcp-servers/{id}/oauth/authorize/."""

    def _server(self, **cfg):
        return MCPServer.objects.create(
            company=self.company, project=self.p1, name="Road test",
            transport=MCPServer.Transport.HTTP, url="https://modern.example/mcp",
            auth_type=MCPServer.AuthType.OAUTH2, oauth_config=cfg,
        )

    def test_connect_click_auto_registers_and_the_url_carries_pkce(self):
        server = self._server(scopes=["mcp.read"])
        fake_post = lambda url, json=None, timeout=None: FakeResp(201, {"client_id": "dyn-client-123"})
        with patch("intelligence.oauth_client.httpx.get", _fake_get_factory()), \
             patch("intelligence.oauth_client.httpx.post", fake_post), \
             self.settings(NEURALOPS_SERVER_URL="http://nucleus.test"):
            r = self.call("get", f"/api/v1/mcp-servers/{server.id}/oauth/authorize/?frontend_origin=http://localhost:3000", self.owner)
        self.assertEqual(r.status_code, 200, r.content)
        url = r.json()["authorize_url"]
        self.assertIn("https://auth.modern.example/authorize", url)
        self.assertIn("client_id=dyn-client-123", url)
        self.assertIn("code_challenge=", url)             # PKCE is on the URL…
        self.assertIn("code_challenge_method=S256", url)  # …and it is S256
        server.refresh_from_db()
        self.assertEqual(server.oauth_config["client_id"], "dyn-client-123")

    def test_a_provider_without_registration_becomes_a_502_with_the_reason(self):
        server = self._server()
        meta = {k: v for k, v in AUTH_META.items() if k != "registration_endpoint"}
        with patch("intelligence.oauth_client.httpx.get", _fake_get_factory(auth_meta=meta)):
            r = self.call("get", f"/api/v1/mcp-servers/{server.id}/oauth/authorize/?frontend_origin=http://x", self.owner)
        self.assertEqual(r.status_code, 502, r.content)
        self.assertIn("paste", r.json()["detail"])  # shown verbatim next to Connect

    def test_portal_relay_mode_points_the_provider_at_the_portal_and_state_carries_home(self):
        server = self._server(
            client_id="vendor-neuralops", authorize_endpoint="https://provider.example/authorize",
            token_endpoint="https://provider.example/token", scopes=["read"],
            redirect_mode="portal_relay",
        )
        from urllib.parse import parse_qs, unquote, urlsplit
        with self.settings(NEURALOPS_PORTAL_URL="https://neuralopsnexus.ai",
                           NEURALOPS_SERVER_URL="http://customer-box.test"):
            url = oauth_client.build_authorize_url(server, frontend_origin="http://localhost:3000")
        qs = parse_qs(urlsplit(url).query)
        self.assertEqual(qs["redirect_uri"], ["https://neuralopsnexus.ai/oauth/relay"])
        # The relay reads server_url WITHOUT the signing key (django signing is
        # signed, not encrypted) -- so it must be IN the state, and the signed
        # load must agree with the plain base64 read.
        state = unquote(qs["state"][0])
        data = signing.loads(state, salt=oauth_client._SIGNING_SALT)
        self.assertEqual(data["server_url"], "http://customer-box.test")
        import base64, json as jsonlib
        segment = state.split(":")[0]
        plain = jsonlib.loads(base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4)))
        self.assertEqual(plain["server_url"], "http://customer-box.test")

    def test_the_callback_exchange_carries_the_code_verifier_from_state(self):
        server = self._server(
            client_id="c", authorize_endpoint="https://p/a", token_endpoint="https://p/t",
            token_env_var="MODERN_TOKEN",
        )
        state = signing.dumps(
            {"server_id": str(server.id), "frontend_origin": "http://localhost:3000",
             "code_verifier": "the-exact-verifier", "server_url": "http://x"},
            salt=oauth_client._SIGNING_SALT,
        )
        with patch("intelligence.oauth_client.OAuth2Client.fetch_token") as fetch:
            fetch.return_value = {"access_token": "at", "refresh_token": "rt", "expires_in": 3600}
            result = oauth_client.complete_callback(code="the-code", state=state)
        self.assertEqual(result["server_id"], str(server.id))
        self.assertEqual(fetch.call_args.kwargs["code_verifier"], "the-exact-verifier")
        server.refresh_from_db()
        self.assertEqual(server.get_secrets()["MODERN_TOKEN"], "at")

    def test_the_catalog_presets_exist_for_exactly_the_famous_three_and_carry_no_secret(self):
        r = self.call("get", "/api/v1/mcp-catalog/", self.sara)
        self.assertEqual(r.status_code, 200, r.content)
        rows = {e["id"]: e for e in r.json()}
        with_preset = {i for i, e in rows.items() if e.get("oauth_preset")}
        self.assertEqual(with_preset, {"github", "atlassian", "google-drive"})  # the owner's ruling: ONLY these
        for entry_id in with_preset:
            preset = rows[entry_id]["oauth_preset"]
            self.assertEqual(preset["redirect_mode"], "portal_relay")
            self.assertTrue(preset["authorize_endpoint"].startswith("https://"))
            self.assertTrue(preset["token_endpoint"].startswith("https://"))
            self.assertNotIn("client_secret", preset)   # the secret NEVER ships
