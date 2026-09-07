"""
Management command: python manage.py test_auth_flow

Exercises the Supabase-facing seams without touching Supabase:

    1  verify_supabase_token -- tokens signed with a throwaway ES256 key
       against a stubbed JWKS client: valid / expired / wrong audience /
       no email / unknown kid (another project) / keys unreachable, each
       with the SupabaseTokenError.code the API layer surfaces.
    2  invite_to_system -- the invitation email seam (_send_invite_email)
       with invite_user_by_email stubbed: no service key -> nothing sent;
       key set -> sent, with this server seeded into the invitee's launcher
       metadata; address already registered -> not sent, explained.

Same shape as the other test_*_flow commands: safe to re-run (test
invitations use @example.test addresses and are removed first).
"""
import time
import uuid

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from django.core.management.base import BaseCommand
from django.test.utils import override_settings
from jwt import PyJWKClientConnectionError, PyJWKClientError

from authn import supabase as sb
from nucleus.models import Company, Invitation
from workspace import services as wsvc


class _Key:
    def __init__(self, key):
        self.key = key


class _StubJWKS:
    """Stands in for PyJWKClient: returns the test public key, or raises."""

    def __init__(self, public_key, raise_with=None):
        self.public_key = public_key
        self.raise_with = raise_with

    def get_signing_key_from_jwt(self, token):
        if self.raise_with:
            raise self.raise_with
        return _Key(self.public_key)


class Command(BaseCommand):
    help = "Exercise token verification and the invitation-email seam with Supabase stubbed out."

    def handle(self, *args, **options):
        self._line()
        self.stdout.write(self.style.NOTICE("Auth flow test (token verification + invitation email seam)"))
        self._line()

        private = ec.generate_private_key(ec.SECP256R1())
        private_pem = private.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        )
        public = private.public_key()
        from django.conf import settings
        iss, aud = settings.SUPABASE_JWT_ISSUER, settings.SUPABASE_JWT_AUDIENCE

        def token(**over):
            claims = {"sub": "u-1", "email": "auth-flow@example.test", "iss": iss, "aud": aud,
                      "iat": int(time.time()) - 10, "exp": int(time.time()) + 600}
            claims.update(over)
            claims = {k: v for k, v in claims.items() if v is not None}
            return jwt.encode(claims, private_pem, algorithm="ES256", headers={"kid": "test"})

        real_client = sb.jwks_client
        try:
            sb.jwks_client = _StubJWKS(public)
            self._section("1 -- verify_supabase_token")
            claims = sb.verify_supabase_token(token())
            self._check("valid token yields its claims", claims.get("email"), "auth-flow@example.test")
            self._check("expired token -> code expired", self._code(lambda: sb.verify_supabase_token(token(exp=int(time.time()) - 5))), "expired")
            self._check("wrong audience -> code wrong_project", self._code(lambda: sb.verify_supabase_token(token(aud="other"))), "wrong_project")
            self._check("wrong issuer -> code wrong_project", self._code(lambda: sb.verify_supabase_token(token(iss="https://elsewhere.supabase.co/auth/v1"))), "wrong_project")
            self._check("no email claim -> code no_email", self._code(lambda: sb.verify_supabase_token(token(email=None))), "no_email")
            self._check("garbage -> code invalid", self._code(lambda: sb.verify_supabase_token("not.a.token")), "invalid")
            sb.jwks_client = _StubJWKS(public, raise_with=PyJWKClientError("Unable to find a signing key that matches"))
            self._check("unknown kid (another project) -> code wrong_project", self._code(lambda: sb.verify_supabase_token(token())), "wrong_project")
            sb.jwks_client = _StubJWKS(public, raise_with=PyJWKClientConnectionError("boom"))
            self._check("JWKS unreachable -> code keys_unavailable", self._code(lambda: sb.verify_supabase_token(token())), "keys_unavailable")
        finally:
            sb.jwks_client = real_client

        self._section("2 -- invite_to_system: the invitation email seam")
        company = Company.objects.filter(is_active=True).first()
        if not company or not company.owner:
            self.stdout.write(self.style.ERROR("  no company/owner -- run create_owner first"))
            return
        Invitation.objects.filter(email__endswith="@example.test").delete()  # test rows only

        calls = []
        real_invite = sb.invite_user_by_email

        def stub_ok(email, redirect_to="", metadata=None):
            calls.append({"email": email, "redirect_to": redirect_to, "metadata": metadata})
            return {"id": "sb-user"}

        def stub_exists(email, redirect_to="", metadata=None):
            raise sb.SupabaseAdminError("Supabase invite failed: A user with this email address has already been registered", code="exists")

        try:
            sb.invite_user_by_email = stub_ok
            with override_settings(SUPABASE_SERVICE_KEY="", NEURALOPS_SERVER_URL="https://nexus.example.test"):
                r = wsvc.invite_to_system(company, company.owner, f"nokey-{uuid.uuid4().hex[:6]}@example.test", redirect_to="https://app.example.test/reset-password")
            self._check("no service key -> pending invite, no email", (r["is_new_user"], r["email_sent"], r["email_note"]), (True, False, None))
            self._check("no service key -> no admin call", len(calls), 0)

            with override_settings(SUPABASE_SERVICE_KEY="service-key", NEURALOPS_SERVER_URL="https://nexus.example.test"):
                r = wsvc.invite_to_system(company, company.owner, f"sent-{uuid.uuid4().hex[:6]}@example.test", redirect_to="https://app.example.test/reset-password")
            self._check("service key -> email sent", (r["is_new_user"], r["email_sent"], r["email_note"]), (True, True, None))
            self._check("admin invite called once with the redirect", (len(calls), calls[-1]["redirect_to"]), (1, "https://app.example.test/reset-password"))
            seeded = (calls[-1]["metadata"] or {}).get("nx_servers") or []
            self._check("invitee's launcher seeded with this server", (len(seeded), seeded[0]["url"] if seeded else None, seeded[0]["name"] if seeded else None), (1, "https://nexus.example.test", company.name))

            with override_settings(SUPABASE_SERVICE_KEY="service-key", NEURALOPS_SERVER_URL="https://nexus.example.test"):
                r = wsvc.invite_to_system(company, company.owner, f"badurl-{uuid.uuid4().hex[:6]}@example.test", redirect_to="javascript:alert(1)")
            self._check("non-http redirect_to is dropped", calls[-1]["redirect_to"], "")

            sb.invite_user_by_email = stub_exists
            with override_settings(SUPABASE_SERVICE_KEY="service-key", NEURALOPS_SERVER_URL="https://nexus.example.test"):
                r = wsvc.invite_to_system(company, company.owner, f"exists-{uuid.uuid4().hex[:6]}@example.test")
            self._check("already registered -> not sent, explained", (r["email_sent"], "already" in (r["email_note"] or "")), (False, True))
            self._check("pending Invitation still created", Invitation.objects.filter(email=r["email"], status=Invitation.Status.PENDING).exists(), True)
        finally:
            sb.invite_user_by_email = real_invite
            Invitation.objects.filter(email__endswith="@example.test").delete()

        self._line()
        self.stdout.write("Done.")

    # ── helpers ──────────────────────────────────────────────────────────────
    def _code(self, fn):
        try:
            fn()
            return None
        except sb.SupabaseTokenError as exc:
            return exc.code

    def _section(self, title):
        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING(f"-- {title} --"))

    def _check(self, label, actual, expected):
        ok = actual == expected
        tag = self.style.SUCCESS("[PASS]") if ok else self.style.ERROR("[FAIL]")
        self.stdout.write(f"  {tag} {label}: {actual!r} (expected {expected!r})")

    def _line(self):
        self.stdout.write("=" * 78)
