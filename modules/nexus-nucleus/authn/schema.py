from typing import Dict, List, Optional

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
    # Self-host version check (#170) -- FAT_VERSION for the fat profile,
    # "dev" for the dev profile. Frontend compares this against
    # COMPATIBLE_SERVER_VERSION (lib/version.ts) and prompts an update if
    # they differ -- see ServerList.tsx.
    server_version: Optional[str] = None
    # Per-module versions -- informational only, NOT used in the
    # compatibility check above (that only reads server_version, and only
    # understands plain MAJOR.MINOR.PATCH semver). Sourced from each
    # module's own VERSION file, see core/settings.py.
    nucleus_version: Optional[str] = None
    nexus_ai_version: Optional[str] = None
    nexus_transport_version: Optional[str] = None


# ── Effective permissions ────────────────────────────────────────────────────

class CompanyPermissionsOut(Schema):
    id: str
    rights: List[str]


class MyPermissionsOut(Schema):
    """
    GET /api/v1/me/permissions/ -- what the signed-in user may do, per object.

    `projects` and `topics` are keyed by id. Every list is already resolved for
    reach, so the client does a flat lookup; an absent key means no rights on
    that object.
    """
    company: CompanyPermissionsOut
    projects: Dict[str, List[str]]
    topics: Dict[str, List[str]]
