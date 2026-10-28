"""
Step 4 — login + posture (docs/NUCLEUS-REVAMP.md).

The device-code claim: the person who installed the server runs
`manage.py create_owner` in ITS terminal — it shows a code, the person signs
in at the portal and types it there, and the first VERIFIED person becomes
the owner — with real RBAC rights the moment the claim returns. RULING
(owner, 2026-10-18): the terminal is the ONLY way to start setup — the old
web roads (/setup/start/ and /setup/poll/) are gone, and a test below pins
them closed. Local passwords:
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
    """Fresh install — no company, no owner (so NOT the Mention fixture).

    The claim logic lives in authn.services.claim_install — the ONE creation
    path both create_owner roads end in — so it is tested there. The web
    roads that used to drive it are gone (ruling 2026-10-18), and the last
    test pins them closed.
    """

    def claim(self, workspace_name=None):
        from authn.services import claim_install
        return claim_install(CLAIMS, workspace_name)

    def test_status_says_a_fresh_install_needs_an_owner(self):
        r = Client().get("/api/v1/auth/setup/status/")
        self.assertEqual(r.status_code, 200, r.content)
        body = r.json()
        self.assertTrue(body["needs_owner"])
        self.assertTrue(body["portal_url"])

    def test_the_first_verified_person_becomes_the_owner(self):
        user, company = self.claim(workspace_name="Acme")
        self.assertEqual((user.email, company.name), ("founder@acme.test", "Acme"))

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
        from authn.services import SetupError
        self.claim()
        with self.assertRaises(SetupError):
            self.claim()
        self.assertEqual(Company.objects.count(), 1)
        r = Client().get("/api/v1/auth/setup/status/")
        self.assertFalse(r.json()["needs_owner"])

    def test_a_claim_with_no_email_is_refused(self):
        from authn.services import SetupError, claim_install
        with self.assertRaises(SetupError):
            claim_install({"sub": "sb-1"})
        self.assertFalse(Company.objects.exists())

    def test_the_web_setup_roads_are_closed(self):
        """RULING (owner, 2026-10-18): nobody can start a claim from the
        network — only the server's own terminal (create_owner). These roads
        existing again would reopen the takeover race; this test is the lock
        on the door."""
        for road in ("/api/v1/auth/setup/start/", "/api/v1/auth/setup/poll/"):
            r = Client().post(road, data={}, content_type="application/json")
            self.assertIn(r.status_code, (404, 405), f"{road} answered {r.status_code}")
        self.assertFalse(Company.objects.exists())


class OwnerReservationTests(TestCase):
    """
    Task 2.1 — one-click demo servers (create_owner --email).
    """

    def test_reserved_email_verified_becomes_owner_and_reservation_gone(self):
        from django.core.management import call_command
        from authn.models import OwnerReservation
        from authn.permissions.checker import PermissionChecker
        from authn.services import auth_verify

        call_command("create_owner", email="Demo@Example.com")
        self.assertTrue(OwnerReservation.objects.filter(email="demo@example.com").exists())

        claims = {"email": "Demo@Example.com", "sub": "sb-demo-1", "email_verified": True}
        with patch("authn.services.verify_supabase_token", return_value=claims):
            res = auth_verify("valid-token")

        self.assertTrue(res["ok"])
        self.assertTrue(res["company_exists"])
        self.assertTrue(res["is_owner"])
        self.assertEqual(res["company_name"], "Demo's Workspace")

        # Reservation is gone
        self.assertFalse(OwnerReservation.objects.exists())

        # Owner is created and has real rights
        company = Company.objects.get()
        user = User.objects.get(email="Demo@Example.com")
        self.assertEqual(company.owner_id, user.id)
        self.assertEqual(user.current_company_id, company.id)
        self.assertTrue(PermissionChecker.can(user, "role.update", company=company))

    def test_different_email_refused_no_owner_or_user_created(self):
        from django.core.management import call_command
        from authn.models import OwnerReservation
        from authn.services import auth_verify

        call_command("create_owner", email="demo@example.com")

        # Direct service call raises PermissionError
        claims = {"email": "intruder@example.com", "sub": "sb-intruder", "email_verified": True}
        with patch("authn.services.verify_supabase_token", return_value=claims):
            with self.assertRaises(PermissionError) as cm:
                auth_verify("intruder-token")
            self.assertEqual(str(cm.exception), "This server is reserved for its demo owner.")

        # API endpoint returns 403 Forbidden
        with patch("authn.services.verify_supabase_token", return_value=claims):
            r = Client().get("/api/v1/auth/verify/", HTTP_AUTHORIZATION="Bearer intruder-token")
            self.assertEqual(r.status_code, 403)
            self.assertIn("This server is reserved for its demo owner.", r.json()["detail"])

        # Nothing was created
        self.assertFalse(Company.objects.exists())
        self.assertFalse(User.objects.filter(email="intruder@example.com").exists())
        self.assertEqual(OwnerReservation.objects.count(), 1)

    def test_right_email_unverified_refused(self):
        from django.core.management import call_command
        from authn.models import OwnerReservation
        from authn.services import auth_verify

        call_command("create_owner", email="demo@example.com")

        claims = {"email": "demo@example.com", "sub": "sb-demo", "email_verified": False}
        with patch("authn.services.verify_supabase_token", return_value=claims):
            with self.assertRaises(PermissionError) as cm:
                auth_verify("unverified-token")
            self.assertEqual(str(cm.exception), "This server is reserved for its demo owner.")

        with patch("authn.services.verify_supabase_token", return_value=claims):
            r = Client().get("/api/v1/auth/verify/", HTTP_AUTHORIZATION="Bearer unverified-token")
            self.assertEqual(r.status_code, 403)

        self.assertFalse(Company.objects.exists())
        self.assertFalse(User.objects.filter(email="demo@example.com").exists())
        self.assertEqual(OwnerReservation.objects.count(), 1)

    def test_second_sign_in_after_claim_is_normal_sign_in(self):
        from django.core.management import call_command
        from authn.models import OwnerReservation
        from authn.services import auth_verify

        call_command("create_owner", email="demo@example.com")
        claims = {"email": "demo@example.com", "sub": "sb-demo", "email_verified": True}
        with patch("authn.services.verify_supabase_token", return_value=claims):
            r1 = auth_verify("token-1")
        self.assertTrue(r1["ok"])
        self.assertTrue(r1["is_owner"])
        self.assertEqual(OwnerReservation.objects.count(), 0)

        # Second sign-in with same user
        with patch("authn.services.verify_supabase_token", return_value=claims):
            r2 = auth_verify("token-2")
        self.assertTrue(r2["ok"])
        self.assertTrue(r2["is_owner"])
        self.assertEqual(Company.objects.count(), 1)

    def test_create_owner_email_when_owner_exists_refused(self):
        from django.core.management import call_command
        from authn.models import OwnerReservation
        from authn.services import claim_install

        claim_install(CLAIMS)
        self.assertEqual(Company.objects.count(), 1)

        with self.assertRaises(SystemExit) as cm:
            call_command("create_owner", email="another@example.com")
        self.assertEqual(cm.exception.code, 1)
        self.assertEqual(OwnerReservation.objects.count(), 0)

    def test_code_flow_claim_while_reservation_exists_refused(self):
        from django.core.management import call_command
        from authn.models import OwnerReservation
        from authn.services import SetupError, claim_install

        call_command("create_owner", email="demo@example.com")
        self.assertEqual(OwnerReservation.objects.count(), 1)

        # Normal create_owner without --email refuses
        with self.assertRaises(SystemExit) as cm:
            call_command("create_owner")
        self.assertEqual(cm.exception.code, 1)

        # Direct claim_install with different claims refuses
        with self.assertRaises(SetupError) as cm:
            claim_install({"email": "someone@example.com", "sub": "sb-2", "email_verified": True})
        self.assertEqual(str(cm.exception), "This server is reserved for its demo owner.")
        self.assertFalse(Company.objects.exists())

    def test_create_owner_email_twice_second_reservation_wins(self):
        from django.core.management import call_command
        from authn.models import OwnerReservation

        call_command("create_owner", email="first@example.com")
        self.assertEqual(OwnerReservation.objects.get().email, "first@example.com")

        call_command("create_owner", email="Second@Company.Com")
        self.assertEqual(OwnerReservation.objects.count(), 1)
        self.assertEqual(OwnerReservation.objects.get().email, "second@company.com")


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
