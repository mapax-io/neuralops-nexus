"""
Models: POST /api/v1/models/check/ -- verify a model with its key before
nucleus saves it (apps/managers/model_check.py). Internal only.
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from apps.managers.model_check import check_model
from apps.routers.internal_key import verify_internal_key
from apps.schemas.trigger import ModelConfig

router = APIRouter(prefix="/api/v1", tags=["models"])


class ModelCheckIn(BaseModel):
    provider: str
    model_id: str
    api_key: str | None = None
    api_base: str | None = None


@router.post("/models/check/")
async def check(payload: ModelCheckIn, _: str = Depends(verify_internal_key)) -> dict:
    return await check_model(ModelConfig(provider=payload.provider, model_id=payload.model_id, api_key=payload.api_key, api_base=payload.api_base))
