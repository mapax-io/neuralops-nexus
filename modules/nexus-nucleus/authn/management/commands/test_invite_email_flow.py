"""
Management command: python manage.py test_invite_email_flow

Exercises the invitation email seam (workspace/services.py:_send_invite_email)
with the Supabase admin call stubbed: no service key -> nothing sent; key set
-> sent to the redirect, with this server seeded into the invitee's launcher;
address already registered -> not sent, explained. Safe to re-run (test
invitations use @example.test addresses and are removed first).
"""
import uuid

from django.core.management.base import BaseCommand
from django.test.utils import override_settings

from authn import supabase as sb
from nucleus.models import Company, Invitation
from workspace import services as wsvc


class Command(BaseCommand):
    help = "Exercise the invitation email seam with the Supabase admin call stubbed."

    def handle(self, *args, **options):
        company = Company.objects.filter(is_active=True).first()
        if not company or not company.owner:
            self.stdout.write(self.style.ERROR("no company/owner -- run create_owner first"))
            return
        Invitation.objects.filter(email__endswith="@example.test").delete()
        calls = []
        real = sb.invite_user_by_email

        def stub_ok(email, redirect_to="", metadata=None):
            calls.append({"email": email, "redirect_to": redirect_to, "metadata": metadata})
            return {"id": "sb-user"}

        def stub_exists(email, redirect_to="", metadata=None):
            raise sb.SupabaseAdminError("Supabase invite failed: already been registered", code="exists")

        env = {"NEURALOPS_SERVER_URL": "https://nexus.example.test"}
        try:
            sb.invite_user_by_email = stub_ok
            with override_settings(SUPABASE_SERVICE_KEY="", **env):
                r = wsvc.invite_to_system(company, company.owner, f"nokey-{uuid.uuid4().hex[:6]}@example.test", redirect_to="https://app.example.test/reset-password")
            self._check("no service key -> pending invite, no email", (r["is_new_user"], r["email_sent"], r["email_note"], len(calls)), (True, False, None, 0))
            with override_settings(SUPABASE_SERVICE_KEY="service-key", **env):
                r = wsvc.invite_to_system(company, company.owner, f"sent-{uuid.uuid4().hex[:6]}@example.test", redirect_to="https://app.example.test/reset-password")
            seeded = (calls[-1]["metadata"] or {}).get("nx_servers") or []
            self._check("service key -> email sent to the redirect", (r["email_sent"], r["email_note"], calls[-1]["redirect_to"]), (True, None, "https://app.example.test/reset-password"))
            self._check("invitee's launcher seeded with this server", (len(seeded), seeded[0]["url"] if seeded else None), (1, "https://nexus.example.test"))
            with override_settings(SUPABASE_SERVICE_KEY="service-key", **env):
                wsvc.invite_to_system(company, company.owner, f"badurl-{uuid.uuid4().hex[:6]}@example.test", redirect_to="javascript:alert(1)")
            self._check("non-http redirect_to is dropped", calls[-1]["redirect_to"], "")
            sb.invite_user_by_email = stub_exists
            with override_settings(SUPABASE_SERVICE_KEY="service-key", **env):
                r = wsvc.invite_to_system(company, company.owner, f"exists-{uuid.uuid4().hex[:6]}@example.test")
            self._check("already registered -> not sent, explained", (r["email_sent"], "already" in (r["email_note"] or "")), (False, True))
            self._check("pending Invitation still created", Invitation.objects.filter(email=r["email"], status=Invitation.Status.PENDING).exists(), True)
        finally:
            sb.invite_user_by_email = real
            Invitation.objects.filter(email__endswith="@example.test").delete()
        self.stdout.write("Done.")

    def _check(self, label, actual, expected):
        ok = actual == expected
        tag = self.style.SUCCESS("[PASS]") if ok else self.style.ERROR("[FAIL]")
        self.stdout.write(f"  {tag} {label}: {actual!r} (expected {expected!r})")
