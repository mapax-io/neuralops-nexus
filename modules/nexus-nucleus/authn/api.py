from ninja import Router
from ninja.errors import HttpError

from .schema import SignInRequest, SignInResponse
from .services import signin_with_supabase_token, SignInError
from .supabase import SupabaseTokenError


router = Router(tags=["Authentication"])


@router.post("/signin", response=SignInResponse)
def signin(request, payload: SignInRequest):
    try:
        return signin_with_supabase_token(payload.access_token)
    except (SignInError, SupabaseTokenError) as exc:
        raise HttpError(401, str(exc))
