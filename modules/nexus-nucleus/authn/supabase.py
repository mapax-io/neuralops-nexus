import json
import urllib.request

import jwt
from jwt import PyJWKClient

from django.conf import settings


class SupabaseTokenError(Exception):
    pass


class SupabaseAdminError(Exception):
    pass


jwks_client = PyJWKClient(settings.SUPABASE_JWKS_URL)


def verify_supabase_token(access_token: str) -> dict:
    try:
        signing_key = jwks_client.get_signing_key_from_jwt(access_token)

        claims = jwt.decode(
            access_token,
            signing_key.key,
            algorithms=["ES256", "RS256"],
            audience=settings.SUPABASE_JWT_AUDIENCE,
            issuer=settings.SUPABASE_JWT_ISSUER,
        )

        if not claims.get("sub"):
            raise SupabaseTokenError("Missing Supabase user id.")

        if not claims.get("email"):
            raise SupabaseTokenError("Missing email.")

        return claims

    except Exception as exc:
        raise SupabaseTokenError("Invalid Supabase token.") from exc


def invite_user_by_email(email: str, redirect_to: str = "", metadata: dict = None) -> dict:
    """
    Call Supabase Admin API to invite a user by email.
    Supabase sends the invitation email with a magic link.
    Requires SUPABASE_SERVICE_KEY (service role key from Supabase dashboard).

    Args:
        email:       The invitee's email address.
        redirect_to: Where Supabase redirects after the user clicks the link.
        metadata:    Extra user_metadata stored on the Supabase user (e.g. invitation token).

    Returns dict with Supabase user object on success.
    Raises SupabaseAdminError on failure.
    """
    service_key = settings.SUPABASE_SERVICE_KEY
    if not service_key:
        raise SupabaseAdminError(
            "SUPABASE_SERVICE_KEY is not configured. "
            "Add it to your .env file (Supabase Dashboard → Settings → API → service_role key)."
        )

    url = f"{settings.SUPABASE_URL}/auth/v1/invite"

    payload = {"email": email}
    if redirect_to:
        payload["redirect_to"] = redirect_to
    if metadata:
        payload["data"] = metadata

    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {service_key}",
            "apikey": service_key,
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode(errors="replace")
        try:
            detail = json.loads(raw).get("msg") or json.loads(raw).get("message") or raw
        except Exception:
            detail = raw
        raise SupabaseAdminError(f"Supabase invite failed: {detail}") from exc
    except Exception as exc:
        raise SupabaseAdminError(f"Supabase invite error: {exc}") from exc