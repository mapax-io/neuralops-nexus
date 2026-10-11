"""
The nexus-ai service — a new FastAPI project (docs/NEXUS-AI-REVAMP.md §1.3).

No public port: nucleus reaches it container-to-container on the Docker
network; the internal key check is the second lock.
"""
from __future__ import annotations

import logging
import os

from fastapi import FastAPI

from fastapi_app.routers.trigger import router as trigger_router

# pydantic-ai 2.55 prints a startup banner otherwise (§1.5 implementer rules)
os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))


def create_app() -> FastAPI:
    app = FastAPI(title="nexus-ai", docs_url=None, redoc_url=None, openapi_url=None)
    app.include_router(trigger_router)

    @app.get("/healthz")
    async def healthz() -> dict:
        return {"ok": True}

    return app


app = create_app()
