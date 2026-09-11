import json
import urllib.request

import jwt
from jwt import PyJWKClient

from django.conf import settings


class SupabaseTokenError(Exception):
    pass


class SupabaseAdminError(Exception):
    """`code` is "exists" when the address already has an account (Supabase 422)."""

    def __init__(self, message: str, code: str = "failed"):
        super().__init__(message)
        self.code = code


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
        code = "exists" if exc.code == 422 and "regist" in str(detail).lower() else "failed"
        raise SupabaseAdminError(f"Supabase invite failed: {detail}", code=code) from exc
    except Exception as exc:
        raise SupabaseAdminError(f"Supabase invite error: {exc}") from exc


def send_recovery_email(email: str, redirect_to: str = "") -> None:
    """
    Ask Supabase to email a password-reset (sign-in) link. The public
    /recover endpoint sends it for any existing account -- including one that
    was merely invited before and never claimed -- so it is the way in for an
    address the invite endpoint refuses as "already registered".
    Raises SupabaseAdminError on failure.
    """
    import urllib.parse

    api_key = settings.SUPABASE_ANON_KEY or settings.SUPABASE_SERVICE_KEY
    if not api_key:
        raise SupabaseAdminError("No Supabase key is configured for the recovery email.")
    url = f"{settings.SUPABASE_URL}/auth/v1/recover"
    if redirect_to:
        url += "?" + urllib.parse.urlencode({"redirect_to": redirect_to})
    req = urllib.request.Request(
        url,
        data=json.dumps({"email": email}).encode(),
        method="POST",
        headers={"Content-Type": "application/json", "apikey": api_key, "Authorization": f"Bearer {api_key}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10):
            return
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode(errors="replace")
        raise SupabaseAdminError(f"Supabase recovery email failed: {raw[:200]}") from exc
    except Exception as exc:
        raise SupabaseAdminError(f"Supabase recovery email error: {exc}") from exc
