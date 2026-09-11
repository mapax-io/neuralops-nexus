"""
Management command: create_owner

Sets up the first owner of this NeuralOps server.
Verifies identity against Supabase before creating the owner.

Usage:
    python manage.py create_owner
"""

import getpass
import os
import sys

import httpx
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.text import slugify

from authn.supabase import verify_supabase_token, SupabaseTokenError

User = get_user_model()

# The public app users sign in at. Env-overridable so a self-hosted or local
# deployment can point people at its own address instead of ours.
NEURALOPS_APP_URL = os.getenv("NEURALOPS_APP_URL", "https://neuralopsnexus.ai")
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

        # ── Choose how to prove identity ───────────────────────────────────
        # An account created through GitHub -- or any other OAuth provider --
        # has NO password, so grant_type=password can never succeed for it.
        # That used to make such a user unable to own their own server.
        print()
        print("  How do you sign in?")
        print("    1) Email and password")
        print("    2) GitHub, or another provider (paste an access token)")
        choice = input("  Choose [1/2]: ").strip() or "1"

        email = password = ""
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

        # ── Verify with Supabase ───────────────────────────────────────────
        self.stdout.write("\n  Verifying with Supabase...")

        try:
            if token is None:
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

                self._grant_owner_role(company, user)

                # ── Create default permission groups ────────────────────────
                self._create_default_groups(user)

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
            f"\n  Next steps:\n"
            f"    1. Log in at {NEURALOPS_APP_URL}\n"
            f"    2. Create your first project\n"
            f"    3. Add an AI model and create a Persona to start chatting\n"
        )
        print_divider()

    def _grant_owner_role(self, company, user):
        """
        Grant the real RBAC Owner role -- this is what
        authn/permissions/checker.py::PermissionChecker.can() actually reads
        (RoleAssignment), unlike CompanyAccess.role or the Django auth.Group
        rows set up in _create_default_groups below. Without this, the
        server's own owner would fail every PermissionChecker.can() check
        (this was a real bug -- company.owner had no RoleAssignment at all).

        Creates an empty Role row now if `seed_permissions` hasn't run yet
        for this company -- when it does run (it's meant to run right after
        this command, per the documented setup order), it finds this same
        row via get_or_create and populates its RoleRights, so it doesn't
        matter which of the two commands creates the Role row first.
        """
        from authn.permissions.models import Role
        from authn.permissions.checker import PermissionChecker

        owner_role, _ = Role.objects.get_or_create(
            company=company, name="Owner", scope="company",
            defaults={"description": "Default Owner role."},
        )
        PermissionChecker.assign_role(user, owner_role, company, granted_by=None)
        self.stdout.write(self.style.SUCCESS("  ✓ RBAC Owner role granted"))

    def _create_default_groups(self, owner_user):
        """
        Create default permission groups for this server.
        Owner, Admin, Member, Viewer — each with appropriate permissions.
        """
        all_perms = Permission.objects.filter(content_type__app_label="nucleus")

        view_perms = all_perms.filter(codename__startswith="view_")
        add_change_view_perms = all_perms.filter(
            codename__startswith="add_"
        ) | all_perms.filter(
            codename__startswith="change_"
        ) | view_perms

        # Owner group — all permissions
        owner_group, _ = Group.objects.get_or_create(name="Owner")
        owner_group.permissions.set(all_perms)
        owner_user.groups.add(owner_group)

        # Admin group — all except delete on company-level
        admin_group, _ = Group.objects.get_or_create(name="Admin")
        admin_perms = all_perms.exclude(
            codename__in=["delete_company", "remove_company"]
        )
        admin_group.permissions.set(admin_perms)

        # Member group — add/view/change on workspace, view on AI
        member_group, _ = Group.objects.get_or_create(name="Member")
        member_group.permissions.set(add_change_view_perms)

        # Viewer group — view only
        viewer_group, _ = Group.objects.get_or_create(name="Viewer")
        viewer_group.permissions.set(view_perms)

        self.stdout.write(self.style.SUCCESS(
            "  ✓ Default groups created: Owner, Admin, Member, Viewer"
        ))

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
