"""
Reusable Ninja authentication schemes for NeuralOps API endpoints.
"""
from django.contrib.auth import get_user_model
from ninja.security import HttpBearer

from .supabase import SupabaseTokenError, verify_supabase_token

User = get_user_model()


class SupabaseBearer(HttpBearer):
    """
    Validates the Supabase JWT in the Authorization: Bearer header.
    On success, sets request.auth to the Django User instance.
    On failure, Ninja returns HTTP 401 automatically.
    """

    def authenticate(self, request, token: str):
        try:
            claims = verify_supabase_token(token)
        except SupabaseTokenError:
            return None

        email = claims.get("email")
        if not email:
            return None

        user = User.objects.filter(email=email, is_active=True).first()
        if not user:
            return None

        # Attach to request so middleware-aware code can use request.user
        request.user = user
        return user
