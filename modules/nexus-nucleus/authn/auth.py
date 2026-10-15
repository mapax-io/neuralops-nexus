"""
Reusable Ninja authentication schemes for NeuralOps API endpoints.
"""
import jwt
from django.conf import settings
from django.contrib.auth import get_user_model
from ninja.security import HttpBearer

from .local_auth import LocalTokenError, verify_local_token
from .supabase import SupabaseTokenError, verify_supabase_token

User = get_user_model()


class SupabaseBearer(HttpBearer):
    """
    Validates the bearer token in the Authorization header.
    On success, sets request.auth to the Django User instance.
    On failure, Ninja returns HTTP 401 automatically.

    Two kinds of token are accepted (Step 4, docs/NUCLEUS-REVAMP.md):
      - a Supabase JWT (ES256/RS256) — the normal portal sign-in;
      - this server's own local token (HS256, signed with SECRET_KEY) —
        offline sign-in for users who set a local password.
    The token's alg header decides which check runs: Supabase never signs
    with HS256 and our local tokens are only ever HS256, so nothing is
    guessed twice — and a local token never triggers a JWKS fetch, which is
    what lets a fully offline server authenticate at all.
    """

    def authenticate(self, request, token: str):
        try:
            alg = jwt.get_unverified_header(token).get("alg")
        except jwt.PyJWTError:
            alg = None

        if alg == "HS256":
            if not getattr(settings, "LOCAL_LOGIN_ENABLED", True):
                return None
            try:
                claims = verify_local_token(token)
            except LocalTokenError:
                return None
        else:
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
