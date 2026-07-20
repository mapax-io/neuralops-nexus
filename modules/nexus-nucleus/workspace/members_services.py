"""
Business logic for the Members/Invite system.
"""
import hashlib
import secrets
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.utils import timezone

User = get_user_model()


def get_company():
    """Return the single Company on this server, or None."""
    from nucleus.models import Company
    return Company.objects.filter(is_active=True).first()


def get_member_access(company, user):
    """
    Return the CompanyAccess record for user, or None.
    """
    from nucleus.models import CompanyAccess
    return CompanyAccess.objects.filter(
        company=company,
        user=user,
        is_active=True,
    ).first()


def send_invite(company, inviter, email: str, role: str) -> dict:
    """
    Create an Invitation record.
    Returns dict with invitation details.
    Raises ValueError on validation errors.
    """
    from nucleus.models import CompanyAccess, Invitation

    # Validate role
    valid_roles = [r.value for r in CompanyAccess.Role]
    if role not in valid_roles:
        raise ValueError(f"Invalid role '{role}'. Must be one of: {', '.join(valid_roles)}")

    # Already a member?
    if CompanyAccess.objects.filter(
        company=company,
        user__email=email,
        is_active=True,
    ).exists():
        raise ValueError(f"{email} is already a member of this server.")

    # Pending invitation already exists?
    if Invitation.objects.filter(
        company=company,
        email=email,
        status=Invitation.Status.PENDING,
        is_active=True,
    ).exists():
        raise ValueError(f"An active invitation has already been sent to {email}.")

    # Create invitation
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()

    invitation = Invitation.objects.create(
        company=company,
        email=email,
        role=role,
        invited_by=inviter,
        token_hash=token_hash,
        expires_at=timezone.now() + timedelta(days=7),
    )

    # TODO: send email with invite link containing `token`
    # The plain token (not hash) should be emailed — only the hash is stored.

    return {
        "ok": True,
        "message": f"Invitation sent to {email}",
        "email": email,
        "role": role,
        "expires_at": invitation.expires_at.isoformat(),
    }


def list_members(company) -> list:
    """Return all active members with their details."""
    from nucleus.models import CompanyAccess

    members = CompanyAccess.objects.filter(
        company=company,
        is_active=True,
    ).select_related("user", "invited_by")

    return [
        {
            "user_id": str(m.user.id),
            "email": m.user.email,
            "role": m.role,
            "invited_by": m.invited_by.email if m.invited_by else None,
            "joined_at": m.joined_at.isoformat(),
        }
        for m in members
    ]


def remove_member(company, caller, target_user_id: str) -> dict:
    """
    Soft-delete the target member's CompanyAccess.
    Raises ValueError for guard violations.
    """
    from nucleus.models import CompanyAccess

    try:
        target_access = CompanyAccess.objects.get(
            company=company,
            user__id=target_user_id,
            is_active=True,
        )
    except CompanyAccess.DoesNotExist:
        raise ValueError("Member not found.")

    if target_access.role == CompanyAccess.Role.OWNER:
        raise ValueError("Cannot remove the server owner.")

    if target_access.user == caller:
        raise ValueError("You cannot remove yourself.")

    target_access.soft_delete()

    return {
        "ok": True,
        "message": f"{target_access.user.email} has been removed from this server.",
    }
