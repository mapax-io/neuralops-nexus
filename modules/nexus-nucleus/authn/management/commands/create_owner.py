"""
Management command: create_owner

Makes the FIRST owner of this NeuralOps server — and it is the ONLY road to
ownership (owner's ruling, 2026-10-18): starting setup requires this
server's own terminal, which only the person who installed it has. The web
app and the public API deliberately offer NO way to start setup — the old
/auth/setup/start/ and /auth/setup/poll/ roads were removed with this
ruling (docs/NUCLEUS-REVAMP.md).

Default road — the code flow, same shape as Docker's or GitHub's terminal
login:

    python manage.py create_owner

  1. This command asks the portal for a short code and prints it, plus the
     portal link.
  2. The person opens the link in any browser, signs in (or creates their
     account), and types the code there.
  3. This command notices (it polls), verifies the identity the portal
     hands back, and makes that person the owner.

  The code travels terminal → web, carried by eyes. No password ever
  touches this terminal, and nothing is ever pasted into it.

Fallback road — when the portal is unreachable (or there's no browser
anywhere near):

    python manage.py create_owner --manual

  Proves identity with email+password or a pasted access token, directly
  against Supabase.

Both roads end in authn.services.claim_install — ONE creation path
(company, owner, RBAC Owner role, default groups, seed_permissions runs
inside it, display name, avatar). No duplicate creation code here.
"""

import getpass
import os
import sys
import time

import httpx
from django.conf import settings
from django.core.management.base import BaseCommand

from authn.portal import PortalError, poll_device_code, request_device_code
from authn.services import SetupError, claim_install, server_needs_owner
from authn.supabase import SupabaseTokenError, verify_supabase_token

# The public app users sign in at. Env-overridable so a self-hosted or local
# deployment can point people at its own address instead of ours.
NEURALOPS_APP_URL = os.getenv("NEURALOPS_APP_URL", "https://neuralopsnexus.ai")
POLL_SECONDS = 3
DIVIDER = "━" * 50


def print_divider():
    print(DIVIDER)


def print_header():
    print_divider()
    print("  NeuralOps — Server Owner Setup")
    print_divider()


class Command(BaseCommand):
    help = (
        "Claim this server's ownership from its own terminal. Default: shows a "
        "code to type at the portal (like a TV sign-in). --manual: email+password "
        "or a pasted token, for when the portal is unreachable."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--manual",
            action="store_true",
            help="Prove identity with email+password or a pasted access token "
                 "instead of the code flow (fallback when the portal is unreachable).",
        )

    def handle(self, *args, **options):
        from nucleus.models import Company

        print_header()

        # ── Already owned? ──────────────────────────────────────────────────
        company = Company.objects.filter(is_active=True).first()
        if not server_needs_owner():
            self.stdout.write(
                self.style.WARNING(
                    f"\n  ✗ This server already has an owner: {company.owner.email}\n"
                    f"    Company: {company.name}\n\n"
                    f"  If you need to transfer ownership, contact support.\n"
                )
            )
            print_divider()
            sys.exit(1)

        self.stdout.write("\n  No owner found on this server. Let's set one up.\n")

        # ── Prove who is claiming ───────────────────────────────────────────
        if options["manual"]:
            claims = self._claims_via_manual()
        else:
            claims = self._claims_via_code()

        verified_email = claims.get("email")
        self.stdout.write(self.style.SUCCESS(f"\n  ✓ Identity confirmed ({verified_email})\n"))

        # ── Workspace name ──────────────────────────────────────────────────
        default_name = verified_email.split("@")[0].capitalize() + "'s Workspace"
        workspace_name = input(f"  Enter workspace name [{default_name}]: ").strip()

        # ── Create everything (ONE shared path — authn.services.claim_install:
        #    company, owner, RBAC role, groups, seed_permissions, name, avatar)
        try:
            user, company = claim_install(claims, workspace_name or default_name)
        except SetupError as exc:
            self.stderr.write(f"\n  ✗ {exc}\n")
            print_divider()
            sys.exit(1)

        # ── Success ─────────────────────────────────────────────────────────
        self.stdout.write(
            self.style.SUCCESS(
                f"\n  ✓ Workspace created: {company.name}\n"
                f"  ✓ You are now the owner of this server\n"
                f"  ✓ Rights seeded (seed_permissions ran as part of the claim)\n"
            )
        )
        self.stdout.write(
            f"\n  Next steps:\n"
            f"    1. Log in at {NEURALOPS_APP_URL} and connect to this server\n"
            f"    2. Create your first project\n"
            f"    3. Add an AI model and create a Persona to start chatting\n"
        )
        print_divider()

    # =========================================================================
    # Default road: the code flow (terminal shows code → person types it at
    # the portal → this command polls until claimed).
    # =========================================================================

    def _claims_via_code(self) -> dict:
        try:
            out = request_device_code()
        except PortalError as exc:
            self.stderr.write(
                f"\n  ✗ {exc}\n\n"
                f"  No internet here, or the portal is down? Use the fallback:\n"
                f"    python manage.py create_owner --manual\n"
            )
            print_divider()
            sys.exit(1)

        portal_url = getattr(settings, "NEURALOPS_PORTAL_URL", "") or NEURALOPS_APP_URL
        minutes = max(1, out["expires_in"] // 60)

        print()
        print("  To claim this server:")
        print()
        print(f"    1. Open:   {portal_url}")
        print("    2. Sign in (or create your account)")
        print("    3. Type this code there:")
        print()
        print(f"           {out['code']}")
        print()
        print(f"  The code lives {minutes} minutes. Waiting for the claim", end="", flush=True)

        deadline = time.monotonic() + out["expires_in"]
        try:
            while time.monotonic() < deadline:
                time.sleep(POLL_SECONDS)
                print(".", end="", flush=True)
                try:
                    result = poll_device_code(out["request_id"])
                except PortalError as exc:
                    print()
                    self.stderr.write(f"\n  ✗ {exc}\n")
                    print_divider()
                    sys.exit(1)
                if result["status"] == "claimed":
                    print()
                    try:
                        return verify_supabase_token(result["access_token"])
                    except SupabaseTokenError as exc:
                        self.stderr.write(
                            f"\n  ✗ The portal returned a token this server can't verify: {exc}\n"
                        )
                        print_divider()
                        sys.exit(1)
        except KeyboardInterrupt:
            print()
            self.stderr.write("\n  Cancelled. Nothing was changed — run the command again anytime.\n")
            print_divider()
            sys.exit(1)

        print()
        self.stderr.write("\n  ✗ The code expired before anyone claimed it. Run the command again.\n")
        print_divider()
        sys.exit(1)

    # =========================================================================
    # Fallback road: --manual (email+password, or a pasted access token).
    # =========================================================================

    def _claims_via_manual(self) -> dict:
        print()
        has_account = input("  Do you have a NeuralOps account? (yes/no): ").strip().lower()
        if has_account not in ("yes", "y"):
            self.stdout.write(
                f"\n  Please create an account first:\n\n"
                f"    1. Go to {NEURALOPS_APP_URL}/signup\n"
                f"    2. Create your account and verify your email\n"
                f"    3. Come back here and run this command again\n"
            )
            print_divider()
            sys.exit(0)

        # An account created through GitHub -- or any other OAuth provider --
        # has NO password, so grant_type=password can never succeed for it.
        print()
        print("  How do you sign in?")
        print("    1) Email and password")
        print("    2) GitHub, or another provider (paste an access token)")
        choice = input("  Choose [1/2]: ").strip() or "1"

        if choice == "2":
            token = self._prompt_access_token()
        else:
            print()
            email = input("  Enter your email: ").strip()
            password = getpass.getpass("  Enter your password: ")
            if not email or not password:
                self.stderr.write("\n  ✗ Email and password are required.\n")
                sys.exit(1)
            token = None  # exchanged below, inside the error handling

        self.stdout.write("\n  Verifying with Supabase...")
        try:
            if token is None:
                token = self._signin_supabase(email, password)
            return verify_supabase_token(token)
        except SupabaseTokenError as exc:
            self.stderr.write(f"\n  ✗ Verification failed: {exc}\n")
            print_divider()
            sys.exit(1)
        except Exception as exc:
            self.stderr.write(f"\n  ✗ Could not connect to Supabase: {exc}\n")
            print_divider()
            sys.exit(1)

    def _prompt_access_token(self) -> str:
        """
        Take a Supabase access token instead of a password.

        Proves exactly what the password proved -- this person controls this
        account, right now -- but works for every sign-in method rather than
        only for accounts that happen to have a password.

        It also costs this server nothing to check. verify_supabase_token()
        is pure signature verification against the project's published JWKS,
        so validating what is pasted here needs no anon key, no service key
        and no secret of any kind. The token is short-lived (about an hour)
        and is used once, here.

        Read with getpass so a long-lived-looking credential does not end up
        in terminal scrollback or shell history -- input stays hidden while
        pasting, which is expected.
        """
        print()
        print("  Get your access token:")
        print(f"    1. Sign in at {NEURALOPS_APP_URL}")
        print("    2. Open your browser's developer console (F12)")
        print("    3. Run this, and copy the string it prints:")
        print()
        print("       JSON.parse(Object.entries(localStorage).find(([k]) => "
              "k.startsWith('sb-') && k.endsWith('-auth-token'))[1]).access_token")
        print()
        print("  (Input is hidden while you paste.)")
        token = getpass.getpass("  Paste your access token: ").strip()

        if not token:
            self.stderr.write("\n  ✗ An access token is required.\n")
            sys.exit(1)
        return token

    def _signin_supabase(self, email: str, password: str) -> str:
        """
        Sign in to Supabase with email + password.
        Returns the access_token JWT.
        """
        url = f"{settings.SUPABASE_URL}/auth/v1/token?grant_type=password"
        response = httpx.post(
            url,
            json={"email": email, "password": password},
            headers={
                "apikey": settings.SUPABASE_ANON_KEY,
                "Content-Type": "application/json",
            },
            timeout=15,
        )

        if response.status_code == 400:
            raise SupabaseTokenError("Invalid email or password.")
        if response.status_code == 422:
            raise SupabaseTokenError("Invalid email format.")

        response.raise_for_status()
        data = response.json()
        access_token = data.get("access_token")

        if not access_token:
            raise SupabaseTokenError("No access token returned from Supabase.")

        return access_token
