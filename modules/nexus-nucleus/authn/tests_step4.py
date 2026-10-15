"""
Step 4 — login + posture (docs/NUCLEUS-REVAMP.md).

The device-code claim: a fresh install shows a code, the person signs in at
the portal and types it there, and the first VERIFIED person becomes the
owner — with real RBAC rights the moment the claim returns. Local passwords:
anyone sets their own, admins reset others', sign-in is braked against
guessing, and the local token is accepted by the same bearer check every
endpoint uses (that check is exercised for real here — nothing is patched
on the local road).
"""
from unittest.mock import patch

from django.test import Client, TestCase

from chat.stop_signals import MemoryStore
from chat.tests import MentionRightFixture
from nucleus.models import Company, CompanyAccess, User

CLAIMS = {"email": "founder@acme.test", "sub": "sb-1", "email_verified": True}
GOOD_PASSWORD = "orbit-paper-lamp-42"


class SetupFlowTests(TestCase):
    """Fresh install — no company, no owner (so NOT the Mention fixture)."""

    def poll(self, request_id="req-1", workspace_name=None, portal=None):
        payload = {"request_id": request_id}
        if workspace_name:
            payload["workspace_name"] = workspace_name
        with patch("authn.api.poll_device_code", return_value=portal or {"status": "pending"}), \
             patch("authn.api.verify_supabase_token", return_value=CLAIMS):
            return Client().post("/api/v1/auth/setup/poll/", data=payload,
                                 content_type="application/json")

    def test_status_says_a_fresh_install_needs_an_owner(self):
        r = Client().get("/api/v1/auth/setup/status/")
        self.assertEqual(r.status_code, 200, r.content)
        body = r.json()
        self.assertTrue(body["needs_owner"])
        self.assertTrue(body["portal_url"])

    def test_start_hands_out_the_portal_code(self):
        with patch("authn.api.request_device_code",
                   return_value={"code": "ABC-123", "request_id": "req-1", "expires_in": 900}):
            r = Client().post("/api/v1/auth/setup/start/")
        self.assertEqual(r.status_code, 200, r.content)
        body = r.json()
        self.assertEqual((body["code"], body["request_id"]), ("ABC-123", "req-1"))
        self.assertTrue(body["portal_url"])

    def test_poll_waits_while_nobody_typed_the_code(self):
        r = self.poll()
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["status"], "pending")
        self.assertFalse(Company.objects.exists())

    def test_the_first_verified_person_becomes_the_owner(self):
        r = self.poll(workspace_name="Acme",
                      portal={"status": "claimed", "access_token": "sb-token"})
        self.assertEqual(r.status_code, 200, r.content)
        body = r.json()
        self.assertEqual((body["status"], body["email"], body["workspace"]),
                         ("claimed", "founder@acme.test", "Acme"))
        self.assertEqual(body["access_token"], "sb-token")

        company = Company.objects.get()
        user = User.objects.get(email="founder@acme.test")
        self.assertEqual(company.owner_id, user.id)
        self.assertTrue(company.is_personal)
        self.assertEqual(user.current_company_id, company.id)
        self.assertTrue(CompanyAccess.objects.filter(
            company=company, user=user, role=CompanyAccess.Role.OWNER).exists())

        # The REAL rights: seed_permissions ran inside the claim, so the
        # owner can do owner things immediately — PermissionChecker reads
        # RoleAssignment, never CompanyAccess.role (the create_owner bug).
        from authn.permissions.checker import PermissionChecker
        self.assertTrue(PermissionChecker.can(user, "role.update", company=company))
        self.assertTrue(PermissionChecker.can(user, "company.local_password", company=company))

    def test_a_second_claim_is_refused_and_setup_closes(self):
        self.poll(portal={"status": "claimed", "access_token": "sb-token"})
        r = self.poll(portal={"status": "claimed", "access_token": "sb-token"})
        self.assertEqual(r.status_code, 409)
        self.assertEqual(Company.objects.count(), 1)
        with patch("authn.api.request_device_code") as asked:
            r = Client().post("/api/v1/auth/setup/start/")
        self.assertEqual(r.status_code, 409)
        asked.assert_not_called()
        r = Client().get("/api/v1/auth/setup/status/")
        self.assertFalse(r.json()["needs_owner"])

    def test_a_dead_portal_names_the_terminal_fallback(self):
        from authn.portal import PortalError
        with patch("authn.api.request_device_code", side_effect=PortalError("Could not reach the sign-in portal.")):
            r = Client().post("/api/v1/auth/setup/start/")
        self.assertEqual(r.status_code, 502)
        self.assertIn("create_owner", r.json()["detail"])


class LocalAuthTests(MentionRightFixture):
    """Local passwords: set your own, sign in offline, admins reset others'."""

    def local(self, method, path, user, body=None):
        """A call authenticated by a LOCAL token — the bearer fallback for real."""
        from authn.local_auth import issue_local_token
        token = issue_local_token(user)
        return getattr(Client(), method)(path, data=body, content_type="application/json",
                                         HTTP_AUTHORIZATION=f"Bearer {token}")

    def signin(self, email, password, store=None):
        with patch("authn.api.signal_store", return_value=store or MemoryStore()):
            return Client().post("/api/v1/auth/local/signin/",
                                 data={"email": email, "password": password},
                                 content_type="application/json")

    def test_set_your_own_password_then_sign_in_offline(self):
        r = self.local("post", "/api/v1/auth/local/set-password/", self.sara,
                       {"password": GOOD_PASSWORD})
        self.assertEqual(r.status_code, 200, r.content)

        r = self.signin(self.sara.email, GOOD_PASSWORD)
        self.assertEqual(r.status_code, 200, r.content)
        body = r.json()
        self.assertEqual(body["user"]["email"], self.sara.email)
        # The token it handed out opens a normal authenticated endpoint —
        # SupabaseBearer's HS256 road, nothing patched.
        r = Client().get("/api/v1/me/permissions/",
                         HTTP_AUTHORIZATION=f"Bearer {body['access_token']}")
        self.assertEqual(r.status_code, 200, r.content)

    def test_a_weak_password_is_refused_with_the_reason(self):
        r = self.local("post", "/api/v1/auth/local/set-password/", self.sara,
                       {"password": "123"})
        self.assertEqual(r.status_code, 400)
        self.assertTrue(r.json()["detail"])

    def test_wrong_password_and_unknown_email_fail_the_same_way(self):
        wrong = self.signin(self.sara.email, "not-it")
        nobody = self.signin("ghost@acme.test", "not-it")
        self.assertEqual(wrong.status_code, 401)
        self.assertEqual(nobody.status_code, 401)
        self.assertEqual(wrong.json()["detail"], nobody.json()["detail"])

    def test_too_many_wrong_guesses_are_braked(self):
        store = MemoryStore()
        for _ in range(10):
            r = self.signin(self.sara.email, "not-it", store=store)
            self.assertEqual(r.status_code, 401)
        r = self.signin(self.sara.email, "not-it", store=store)
        self.assertEqual(r.status_code, 429)

    def test_local_login_can_be_turned_off_entirely(self):
        with self.settings(LOCAL_LOGIN_ENABLED=False):
            r = self.signin(self.sara.email, GOOD_PASSWORD)
            self.assertEqual(r.status_code, 403)
            # ...and already-issued local tokens stop working too.
            r = self.local("get", "/api/v1/me/permissions/", self.owner)
            self.assertEqual(r.status_code, 401)

    def test_an_expired_local_token_is_refused(self):
        from authn.local_auth import issue_local_token
        with self.settings(LOCAL_TOKEN_HOURS=-1):
            token = issue_local_token(self.owner)
        r = Client().get("/api/v1/me/permissions/", HTTP_AUTHORIZATION=f"Bearer {token}")
        self.assertEqual(r.status_code, 401)

    def test_an_admin_resets_a_members_password_a_member_may_not(self):
        r = self.local("post", "/api/v1/auth/local/reset-password/", self.sara,
                       {"user_id": str(self.vera.id), "password": GOOD_PASSWORD})
        self.assertEqual(r.status_code, 403, r.content)

        r = self.local("post", "/api/v1/auth/local/reset-password/", self.owner,
                       {"user_id": str(self.vera.id), "password": GOOD_PASSWORD})
        self.assertEqual(r.status_code, 200, r.content)

        r = self.signin(self.vera.email, GOOD_PASSWORD)
        self.assertEqual(r.status_code, 200, r.content)

    def test_resetting_a_persona_or_ghost_is_refused(self):
        r = self.local("post", "/api/v1/auth/local/reset-password/", self.owner,
                       {"user_id": str(self.persona_sara.identity_user_id), "password": GOOD_PASSWORD})
        self.assertEqual(r.status_code, 404)
