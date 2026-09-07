from apps.core.logging_config import configure_logging

configure_logging()  # must run before anything else logs at import time

from fastapi import FastAPI, HTTPException
from .routers import embed, mcp, trigger

app = FastAPI(title="NeuralOps nexus-ai", version="1.0.0")

app.include_router(embed.router)
app.include_router(trigger.router)
app.include_router(mcp.router)
