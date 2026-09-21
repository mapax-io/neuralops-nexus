from apps.core.logging_config import configure_logging

configure_logging()  # must run before anything else logs at import time

from fastapi import FastAPI, HTTPException
from .routers import embed, models, terminal, trigger

app = FastAPI(title="NeuralOps nexus-ai", version="1.0.0")

app.include_router(embed.router)
app.include_router(trigger.router)
app.include_router(terminal.router)
app.include_router(models.router)
