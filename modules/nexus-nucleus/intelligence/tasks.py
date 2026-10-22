"""
intelligence/tasks.py — the price-catalog refresh (Step 1, owner's ruling:
"prices can be updated using some API … we will write that prices are not
confirmed, these are estimated").

One celery task fetches a community-maintained public price list and upserts
nucleus.models.ModelPrice rows. It FAILS SILENTLY offline (air-gapped installs
keep their last-known catalog, or the admin's typed overrides). Scheduled
daily via CELERY_BEAT_SCHEDULE in core/settings.py; it can also be fired by
hand:  celery -A core call intelligence.tasks.refresh_model_prices

Source: LiteLLM's model_prices_and_context_window.json — the de-facto shared
price list for every major provider, updated by its community. Its numbers are
per-TOKEN; ours are per-MILLION. Whatever the source says, the UI always
labels money as ESTIMATED.
"""
from __future__ import annotations

import logging
from decimal import Decimal

from celery import shared_task
from django.conf import settings

logger = logging.getLogger(__name__)

# Keys in the source file → our provider names (unmapped providers are kept
# verbatim; the lookup in pricing.py also falls back to bare model_id).
_PROVIDER_MAP = {
    "openai": "openai",
    "anthropic": "anthropic",
    "gemini": "google",
    "vertex_ai-language-models": "google",
    "deepseek": "deepseek",
}


def _per_million(value) -> Decimal | None:
    if value in (None, "", 0) and value != 0:
        return None
    try:
        return Decimal(str(value)) * Decimal(1_000_000)
    except Exception:  # noqa: BLE001
        return None


def _tokens(value) -> int | None:
    """A token COUNT from the source (context window / max output): a positive
    int or None — the catalog file mixes ints, floats and absent keys."""
    try:
        count = int(value)
        return count if count > 0 else None
    except Exception:  # noqa: BLE001
        return None


def upsert_catalog(data: dict, *, source: str = "litellm-catalog", only_missing: bool = False) -> int:
    """
    Parse a litellm-shaped catalog dict and write ModelPrice rows. ONE parser
    for both roads into the DB: the daily online refresh, and the bundled
    seed a new install loads (owner's ruling 2026-10-21: setup pushes default
    data — models, windows, rates — into the DB). With only_missing=True a
    row that already exists is left alone, so the seed never downgrades what
    the fresher online refresh wrote.
    """
    from nucleus.models import ModelPrice

    saved = 0
    for raw_id, row in data.items():
        if not isinstance(row, dict):
            continue
        provider = _PROVIDER_MAP.get(str(row.get("litellm_provider") or ""), "")
        if not provider:
            continue
        model_id = raw_id.split("/", 1)[-1]  # "anthropic/claude-x" → "claude-x"
        inp = _per_million(row.get("input_cost_per_token"))
        out = _per_million(row.get("output_cost_per_token"))
        cached = _per_million(row.get("cache_read_input_token_cost"))
        # Sizes too (ruling 2026-10-21): the register dialog's defaults come
        # from here. max_input_tokens is the context window; older source
        # rows carry only max_tokens, which stands in.
        ctx = _tokens(row.get("max_input_tokens")) or _tokens(row.get("max_tokens"))
        max_out = _tokens(row.get("max_output_tokens"))
        if inp is None and out is None and ctx is None and max_out is None:
            continue
        values = {"input_per_million": inp, "cached_per_million": cached,
                  "output_per_million": out, "context_window": ctx,
                  "max_output_tokens": max_out, "source": source}
        if only_missing:
            _, created = ModelPrice.objects.get_or_create(
                provider=provider, model_id=model_id, defaults=values)
            if not created:
                continue
        else:
            ModelPrice.objects.update_or_create(
                provider=provider, model_id=model_id, defaults=values)
        saved += 1
    return saved


@shared_task(name="intelligence.tasks.refresh_model_prices")
def refresh_model_prices() -> str:
    """Fetch + upsert. Returns a one-line summary (shows up in celery logs)."""
    import httpx

    url = getattr(settings, "MODEL_PRICES_URL", "")
    if not url:
        return "skipped: MODEL_PRICES_URL not set"
    try:
        response = httpx.get(url, timeout=30.0, follow_redirects=True)
        response.raise_for_status()
        data = response.json()
    except Exception as exc:  # noqa: BLE001 — offline installs stay silent
        logger.info("[prices] refresh skipped (offline or source down): %s", exc)
        return f"skipped: {exc}"

    saved = upsert_catalog(data)
    logger.info("[prices] catalog refreshed: %d rows", saved)
    return f"saved {saved} price rows"


# ── Step 3 (handoff change 10): the reindex driver ───────────────────────

# The system default (decision 3): local fastembed, no company-level default.
DEFAULT_EMBEDDER = {"provider": "fastembed", "model_id": "nomic-ai/nomic-embed-text-v1.5"}
REINDEX_POLL_SECONDS = 5
REINDEX_MAX_POLLS = 720  # give a big project an hour before calling it failed


@shared_task(name="intelligence.tasks.reindex_project")
def reindex_project(project_id: str) -> str:
    """
    The embedder changed: drive the engine's rebuild (POST /embed/reindex/,
    then poll status until 'active') and unlock the project. The old index
    stays active under the lock, so a crash here is safe — the project shows
    'failed' and re-saving the embedder retries. The ENDPOINT set
    reindex_status='building' before queueing this task.
    """
    import time

    from chat.nexus_ai import NexusAIClient
    from nucleus.models import Project

    project = Project.objects.filter(id=project_id).first()
    if not project:
        return "gone"
    client = NexusAIClient()
    spec = project.embedder or DEFAULT_EMBEDDER

    ok, detail = client.start_reindex(str(project.company_id), str(project.id), spec)
    if not ok and "build" not in detail.lower():
        # 409 ("…already building…") means a rebuild is running — poll it; any
        # other refusal is a real failure.
        logger.warning("[reindex] project %s refused: %s", project_id, detail)
        Project.objects.filter(id=project_id).update(reindex_status="failed")
        return f"failed: {detail}"

    for _ in range(REINDEX_MAX_POLLS):
        time.sleep(REINDEX_POLL_SECONDS)
        try:
            status = client.reindex_status(str(project.id))
        except Exception as exc:  # noqa: BLE001 — a flaky poll is not a failed rebuild
            logger.info("[reindex] status poll failed for %s: %s", project_id, type(exc).__name__)
            continue
        if status.get("status") == "active":
            Project.objects.filter(id=project_id).update(reindex_status="")
            logger.info("[reindex] project %s active again (%s/%s)", project_id,
                        status.get("done"), status.get("total"))
            return "active"

    logger.warning("[reindex] project %s never came back active — marked failed", project_id)
    Project.objects.filter(id=project_id).update(reindex_status="failed")
    return "failed: timed out"
