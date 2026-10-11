"""
Engine settings, read from the environment.

A plain dataclass read at AISystemFactory.create() time — no pydantic-settings,
no framework. One settings module for the whole service; fastapi_app imports it
(that import direction is allowed; the reverse is not).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


@dataclass(frozen=True)
class EngineSettings:
    nucleus_url: str = field(default_factory=lambda: _env("NEXUS_NUCLEUS_URL", "http://nexus-nucleus:8000").rstrip("/"))
    internal_key: str = field(default_factory=lambda: _env("INTERNAL_API_KEY", "change-me-in-production"))
    history_depth: int = field(default_factory=lambda: int(_env("HISTORY_DEPTH", "10")))          # O3
    keepalive_seconds: float = field(default_factory=lambda: float(_env("KEEPALIVE_SECONDS", "30")))
    nucleus_timeout_seconds: float = field(default_factory=lambda: float(_env("NUCLEUS_TIMEOUT_SECONDS", "10")))
