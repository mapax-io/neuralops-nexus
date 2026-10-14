"""
POST /api/v1/models/check/ (item 40, Layer 2) — verify a model with its key
before nucleus saves it. Internal only; 0.8.0's path and answer shape, kept,
so nucleus's Register/Edit dialogs work unchanged.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ai_engine.pydantic_ai_system.model_check import check_model
from fastapi_app.routers.trigger import _verify_key

router = APIRouter(prefix="/api/v1", tags=["models"])


class ModelCheckIn(BaseModel):
    provider: str
    model_id: str
    api_key: str | None = None
    api_base: str | None = None


@router.post("/models/check/")
async def check(payload: ModelCheckIn, _: str = Depends(_verify_key)) -> dict:
    return await check_model(payload.provider, payload.model_id,
                             payload.api_key, payload.api_base)
