from typing import Literal, Optional

from ninja import Schema


# ── Existing: Supabase JWT sign-in ─────────────────────────────────────────

class SignInRequest(Schema):
    access_token: str


class LocalUserOut(Schema):
    id: str
    email: str
    username: str
    is_new_user: bool


class ExternalIdentityOut(Schema):
    provider: str
    provider_user_id: str
    email: str
    email_verified: bool


class SignInResponse(Schema):
    user: LocalUserOut
    external_identity: ExternalIdentityOut


# ── Device activation flow ──────────────────────────────────────────────────

class AuthInitResponse(Schema):
    status: Literal["authenticated", "unauthenticated"]
    email: Optional[str] = None
    user_id: Optional[str] = None
    session_expires_at: Optional[str] = None
    login_url: Optional[str] = None


class AuthStatusResponse(Schema):
    status: Literal["pending", "active", "session_expired"]
    email: Optional[str] = None
    user_id: Optional[str] = None
    session_expires_at: Optional[str] = None


# ── Server connection verify ─────────────────────────────────────────────────

class AuthVerifyResponse(Schema):
    ok: bool
    email: str
    user_id: str
    is_new_user: bool
    company_exists: bool
    is_owner: bool
    role: Optional[str] = None
    company_name: Optional[str] = None
