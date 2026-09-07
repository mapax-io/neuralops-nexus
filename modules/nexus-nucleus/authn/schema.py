from typing import Optional

from ninja import Schema


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
