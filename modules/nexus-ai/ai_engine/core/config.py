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
    max_loaded_tools: int = field(default_factory=lambda: int(_env("MAX_LOADED_TOOLS", "12")))  # item 1
    # Item 13: a router that hasn't finished within this window is abandoned
    # and the reply falls through to STANDARD (source="router_failed").
    router_timeout_seconds: float = field(default_factory=lambda: float(_env("ROUTER_TIMEOUT_SECONDS", "20")))
    # Item 16 (§4.1 / §3.5's hardcoded numbers become settings):
    # input_budget = context_window − max_output_tokens − loop_headroom;
    # target ≈70% of budget (trim/compact down to), trigger ≈90% (compaction fires).
    budget_loop_headroom: int = field(default_factory=lambda: int(_env("BUDGET_LOOP_HEADROOM", "8192")))
    budget_target_pct: int = field(default_factory=lambda: int(_env("BUDGET_TARGET_PCT", "70")))
    budget_trigger_pct: int = field(default_factory=lambda: int(_env("BUDGET_TRIGGER_PCT", "90")))
    # Layer 3 (items 31/44/24/33). vector_db_url empty = the feature is OFF:
    # no retrieval during replies, embed endpoints answer 503. The URL points
    # at the nexus_vectors database (decision 2 — same pg instance as nucleus).
    vector_db_url: str = field(default_factory=lambda: _env("NEXUS_VECTOR_DB_URL", ""))
    # Where each index's txtai config dir is cached (trial C6: reconnect =
    # saved dir + transform injected in code). Regenerable from the registry.
    vector_config_dir: str = field(default_factory=lambda: _env("VECTOR_CONFIG_DIR", "/tmp/nexus-vector-config"))
    # Decision 9: always-search v1 — the threshold throws away weak hits.
    retrieval_top_k: int = field(default_factory=lambda: int(_env("RETRIEVAL_TOP_K", "6")))
    retrieval_min_score: float = field(default_factory=lambda: float(_env("RETRIEVAL_MIN_SCORE", "0.30")))
    # Item 23 (Layer 4): the output-type classifier's embedder, "provider[:model]".
    # Default = the vector store's local default, ONE cached model in production;
    # tests set "hash" (no downloads).
    classifier_embedder: str = field(default_factory=lambda: _env(
        "CLASSIFIER_EMBEDDER", "fastembed:nomic-ai/nomic-embed-text-v1.5"))
    # Layer 6 (W6 runbooks, legacy value kept): how much of the previous
    # step's reply a runbook step is given — its head.
    runbook_step_context_max: int = field(default_factory=lambda: int(_env("RUNBOOK_STEP_CONTEXT_MAX", "12000")))
    # Item 46 (Layer 6): delegation bounds — calls per reply, seconds per call.
    delegation_max_calls: int = field(default_factory=lambda: int(_env("DELEGATION_MAX_CALLS", "3")))
    delegation_timeout_seconds: float = field(default_factory=lambda: float(_env("DELEGATION_TIMEOUT_SECONDS", "600")))
