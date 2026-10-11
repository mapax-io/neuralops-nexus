"""The shared-secret check every worker route sits behind (nucleus sends X-Internal-Key)."""
from fastapi import Depends, HTTPException
from fastapi.security.api_key import APIKeyHeader

from apps.core.config import settings

_api_key_header = APIKeyHeader(name="X-Internal-Key", auto_error=False)


def verify_internal_key(key: str = Depends(_api_key_header)) -> str:
    if key != settings.INTERNAL_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid internal API key")
    return key
