"""
Reusable Ninja authentication schemes for NeuralOps API endpoints.
"""
from django.contrib.auth import get_user_model
from ninja.errors import HttpError
from ninja.security import HttpBearer

from .supabase import SupabaseTokenError, verify_supabase_token

User = get_user_model()


class SupabaseBearer(HttpBearer):
    """
    Validates the Supabase JWT in the Authorization: Bearer header.
    On success, sets request.auth to the Django User instance.
    On failure, raises a 401 that SAYS WHY (expired, wrong identity
    project, no email claim, unknown here) -- a bare "Unauthorized" left
    clients guessing between "sign in again" and "misconfigured".
    """

    def authenticate(self, request, token: str):
        try:
            claims = verify_supabase_token(token)
        except SupabaseTokenError as exc:
            raise HttpError(401, str(exc))

        email = claims.get("email")
        if not email:
            raise HttpError(401, "This sign-in has no email address.")

        user = User.objects.filter(email=email, is_active=True).first()
        if not user:
            raise HttpError(401, "This account isn't registered on this server yet -- connect to it first.")

        # Attach to request so middleware-aware code can use request.user
        request.user = user
        return user
