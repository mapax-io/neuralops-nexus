import jwt
from jwt import PyJWKClient

from django.conf import settings


class SupabaseTokenError(Exception):
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