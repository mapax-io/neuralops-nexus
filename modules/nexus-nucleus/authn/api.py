from ninja import Router
from ninja.errors import HttpError

from .schema import AuthInitResponse, AuthStatusResponse, AuthVerifyResponse, SignInRequest, SignInResponse
from .services import DeviceAuthError, SignInError, auth_init, auth_status, auth_verify, signin_with_supabase_token
from .supabase import SupabaseTokenError


router = Router(tags=["Authentication"])


# ── Supabase JWT sign-in ─────────────────────────────────────────────────────

@router.post("/signin", response=SignInResponse)
def signin(request, payload: SignInRequest):
    try:
        return signin_with_supabase_token(payload.access_token)
    except (SignInError, SupabaseTokenError) as exc:
        raise HttpError(401, str(exc))


# ── Device activation flow ───────────────────────────────────────────────────

@router.get("/init/", response=AuthInitResponse)
def init(request):
    try:
        return auth_init()
    except DeviceAuthError as exc:
        raise HttpError(502, f"Could not reach activation service: {exc}")


@router.get("/status/", response=AuthStatusResponse)
def status(request):
    return auth_status()


# ── Server connection verify ─────────────────────────────────────────────────

@router.get("/verify/", response=AuthVerifyResponse)
def verify(request):
    """
    Called by the React app when the user clicks Connect on a server.
    Verifies the Supabase JWT and checks if the user is allowed on this server.
    Returns 200 if allowed, 401 if token invalid, 403 if not allowed.
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HttpError(401, "Missing authorization token")

    token = auth_header.split(" ", 1)[1]
    try:
        return auth_verify(token)
    except SupabaseTokenError as exc:
        raise HttpError(401, str(exc))
    except PermissionError as exc:
        raise HttpError(403, str(exc))
