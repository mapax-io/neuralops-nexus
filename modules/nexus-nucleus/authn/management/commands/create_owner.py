"""
Management command: create_owner

Sets up the first owner of this NeuralOps server.
Verifies identity against Supabase before creating the owner.

Usage:
    python manage.py create_owner
"""

import getpass
import sys

import httpx
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.text import slugify

from authn.supabase import verify_supabase_token, SupabaseTokenError

User = get_user_model()

NEURALOPS_APP_URL = "https://neuralops-nexus.mapax.io"
DIVIDER = "━" * 50


def print_divider():
    print(DIVIDER)


def print_header():
    print_divider()
    print("  NeuralOps — Server Owner Setup")
    print_divider()


class Command(BaseCommand):
    help = "Create the owner of this NeuralOps server by verifying Supabase identity."

    def handle(self, *args, **options):
        from nucleus.models import Company, CompanyAccess

        print_header()

        # ── Check if owner already exists ──────────────────────────────────
        company = Company.objects.filter(is_active=True).first()
        if company and company.owner:
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

        # ── Check if user has a Supabase account ───────────────────────────
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

        # ── Get credentials ────────────────────────────────────────────────
        print()
        email = input("  Enter your email: ").strip()
        password = getpass.getpass("  Enter your password: ")

        if not email or not password:
            self.stderr.write("\n  ✗ Email and password are required.\n")
            sys.exit(1)

        # ── Verify with Supabase ───────────────────────────────────────────
        self.stdout.write("\n  Verifying with Supabase...")

        try:
            token = self._signin_supabase(email, password)
            claims = verify_supabase_token(token)
        except SupabaseTokenError as exc:
            self.stderr.write(f"\n  ✗ Verification failed: {exc}\n")
            print_divider()
            sys.exit(1)
        except Exception as exc:
            self.stderr.write(f"\n  ✗ Could not connect to Supabase: {exc}\n")
            print_divider()
            sys.exit(1)

        verified_email = claims.get("email")
        self.stdout.write(self.style.SUCCESS(f"  ✓ Identity confirmed ({verified_email})\n"))

        # ── Workspace name ─────────────────────────────────────────────────
        default_name = verified_email.split("@")[0].capitalize() + "'s Workspace"
        workspace_name = input(f"  Enter workspace name [{default_name}]: ").strip()
        if not workspace_name:
            workspace_name = default_name

        # ── Create company + owner ─────────────────────────────────────────
        try:
            with transaction.atomic():
                user, _ = User.objects.get_or_create(
                    email=verified_email,
                    defaults={"username": verified_email, "is_active": True},
                )

                slug = slugify(workspace_name)
                # Ensure slug uniqueness
                base_slug = slug
                counter = 1
                while Company.objects.filter(slug=slug).exists():
                    slug = f"{base_slug}-{counter}"
                    counter += 1

                company = Company.objects.create(
                    name=workspace_name,
                    slug=slug,
                    is_personal=True,
                    owner=user,
                )

                CompanyAccess.objects.create(
                    company=company,
                    user=user,
                    role=CompanyAccess.Role.OWNER,
                )

                user.current_company = company
                user.save(update_fields=["current_company"])

        except Exception as exc:
            self.stderr.write(f"\n  ✗ Failed to create workspace: {exc}\n")
            print_divider()
            sys.exit(1)

        # ── Success ────────────────────────────────────────────────────────
        self.stdout.write(
            self.style.SUCCESS(
                f"\n  ✓ Workspace created: {company.name}\n"
                f"  ✓ You are now the owner of this server\n"
            )
        )
        self.stdout.write(
            f"\n  Next step — log in at:\n"
            f"    {NEURALOPS_APP_URL}\n"
        )
        print_divider()

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
