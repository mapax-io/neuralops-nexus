"""
Step 4 (docs/NUCLEUS-REVAMP.md) — local (offline) sign-in tokens.

A user who set a local password in their profile can sign in without
Supabase: POST /api/v1/auth/local/signin/ checks the password against
Django's own hash on the User row and hands back a short-lived JWT signed
with this server's SECRET_KEY (HS256). SupabaseBearer (authn/auth.py)
accepts either kind of token by looking at the token's alg header: HS256 is
ours, anything else goes to Supabase verification. No Supabase token ever
uses HS256 (Supabase signs with ES256/RS256), so the two can't be confused
— and an air-gapped server never touches the network to check a local one.

The token proves nothing outside this server: it is signed with this
deployment's own SECRET_KEY (per-deployment, from init-secrets) and carries
iss/aud "neuralops-local".
"""
from __future__ import annotations

from datetime import timedelta

import jwt
from django.conf import settings
from django.utils import timezone

LOCAL_ALGORITHM = "HS256"
LOCAL_ISSUER = "neuralops-local"
LOCAL_AUDIENCE = "neuralops-local"


class LocalTokenError(Exception):
    """An invalid or expired local token."""


def issue_local_token(user) -> str:
    """A fresh local token for `user`, valid LOCAL_TOKEN_HOURS from now."""
    now = timezone.now()
    hours = int(getattr(settings, "LOCAL_TOKEN_HOURS", 24))
    payload = {
        "sub": str(user.id),
        "email": user.email,
        "iss": LOCAL_ISSUER,
        "aud": LOCAL_AUDIENCE,
        "iat": now,
        "exp": now + timedelta(hours=hours),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=LOCAL_ALGORITHM)


def verify_local_token(token: str) -> dict:
    """The claims of a valid local token, or LocalTokenError with the reason."""
    try:
        return jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[LOCAL_ALGORITHM],
            audience=LOCAL_AUDIENCE,
            issuer=LOCAL_ISSUER,
        )
    except jwt.ExpiredSignatureError as exc:
        raise LocalTokenError("Your offline sign-in expired. Sign in again.") from exc
    except jwt.PyJWTError as exc:
        raise LocalTokenError(f"Invalid local token: {exc}") from exc
