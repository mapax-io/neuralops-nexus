from django.contrib.auth import get_user_model
from django.db import transaction

from .supabase import verify_supabase_token


User = get_user_model()


class SignInError(Exception):
    pass


@transaction.atomic
def signin_with_supabase_token(access_token: str) -> dict:
    if not access_token:
        raise SignInError("access_token is required.")

    claims = verify_supabase_token(access_token)

    email = claims.get("email")
    supabase_user_id = claims.get("sub")
    email_verified = claims.get("email_verified", False)

    if not email:
        raise SignInError("Email is missing from Supabase token.")

    user, created = User.objects.get_or_create(
        email=email,
        defaults={
            "username": email,
            "is_active": True,
        },
    )

    changed_fields = []

    if not user.username:
        user.username = email
        changed_fields.append("username")

    if not user.is_active:
        user.is_active = True
        changed_fields.append("is_active")

    if changed_fields:
        user.save(update_fields=changed_fields)

    return {
        "user": {
            "id": str(user.id),
            "email": user.email,
            "username": user.username,
            "is_new_user": created,
        },
        "external_identity": {
            "provider": "supabase",
            "provider_user_id": supabase_user_id,
            "email": email,
            "email_verified": email_verified,
        },
    }