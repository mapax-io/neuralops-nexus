"""
intelligence/usage.py

Usage rows and monthly budgets. One row per model call, written by nucleus
from the worker's message_done event (chat/services.py) with the actor, the
topic and the ModelConfig row that served it. Budgets live on the model: tokens
and dollars per UTC calendar month, independent, first one reached wins; a
warning at 90 %, a stop at 100 % (usage plan, owner decisions 2026-09-14).

Counts only -- the prompt and response never come here (the worker's
AI_REQUEST_DEBUG_LOG file is where a developer reads them).
"""
import logging
import time
from datetime import datetime, timezone as dt_timezone
from decimal import Decimal

import httpx
from django.db.models import Count, F, Q, Sum
from django.utils import timezone

logger = logging.getLogger(__name__)

WARN_AT = Decimal("0.9")
OPENROUTER_HOST = "openrouter.ai"
PROVIDER_CACHE_SECONDS = 300
_provider_cache: dict[str, tuple[float, dict]] = {}


# ── Windows (UTC calendar month) ──────────────────────────────────────────────

def month_start(now=None) -> datetime:
    now = (now or timezone.now()).astimezone(dt_timezone.utc)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def next_month_start(now=None) -> datetime:
    first = month_start(now)
    return first.replace(year=first.year + 1, month=1) if first.month == 12 else first.replace(month=first.month + 1)


# ── Rows ──────────────────────────────────────────────────────────────────────

def record_ai_request(company, *, persona, model_config, actor_id, topic, msg_id, job_id, hop=0,
                      usage: dict | None = None, latency_ms: int = 0, status: str = "success", error: str | None = None):
    """One row for one completed (or failed) model call. `usage` is the worker's UsageData as a dict, or None."""
    from nucleus.models import AIRequestLog

    u = usage or {}
    cost = u.get("cost_usd")
    return AIRequestLog.objects.create(
        company=company,
        job_id=job_id,
        msg_id=msg_id,
        persona=persona,
        model_config=model_config,
        model_id=model_config.model_id if model_config else "",
        provider=model_config.provider if model_config else "",
        actor_id=actor_id or None,
        topic=topic,
        hop=hop or 0,
        prompt_tokens=int(u.get("input_tokens") or 0),
        completion_tokens=int(u.get("output_tokens") or 0),
        cache_read_tokens=int(u.get("cache_read_tokens") or 0),
        cache_write_tokens=int(u.get("cache_write_tokens") or 0),
        requests=int(u.get("requests") or 0),
        tool_calls=int(u.get("tool_calls") or 0),
        cost_usd=Decimal(str(cost)) if cost is not None else None,
        latency_ms=max(0, int(latency_ms or 0)),
        status=AIRequestLog.Status.ERROR if status == "error" else AIRequestLog.Status.SUCCESS,
        error=error,
    )


# ── Totals ────────────────────────────────────────────────────────────────────

TOKENS = F("prompt_tokens") + F("completion_tokens") + F("cache_read_tokens") + F("cache_write_tokens")


def _totals(qs) -> dict:
    agg = qs.aggregate(
        input=Sum("prompt_tokens"), output=Sum("completion_tokens"),
        cache_read=Sum("cache_read_tokens"), cache_write=Sum("cache_write_tokens"),
        total=Sum(TOKENS), requests=Sum("requests"), calls=Count("id"),
        cost=Sum("cost_usd"), unpriced=Count("id", filter=Q(cost_usd__isnull=True)),
    )
    return {
        "input": agg["input"] or 0, "output": agg["output"] or 0,
        "cache_read": agg["cache_read"] or 0, "cache_write": agg["cache_write"] or 0,
        "tokens": agg["total"] or 0, "requests": agg["requests"] or 0, "calls": agg["calls"] or 0,
        "cost_usd": agg["cost"],                 # Decimal, or None when nothing was priced
        "cost_complete": (agg["unpriced"] or 0) == 0,  # every call this window carried a price
    }


def _successful(model_config):
    from nucleus.models import AIRequestLog
    return model_config.request_logs.filter(status=AIRequestLog.Status.SUCCESS)


def month_totals(model_config, now=None) -> dict:
    return _totals(_successful(model_config).filter(created_at__gte=month_start(now)))


def all_time_totals(model_config) -> dict:
    return _totals(_successful(model_config))


# ── Budgets ───────────────────────────────────────────────────────────────────

def budget_state(model_config, totals: dict | None = None) -> dict:
    """
    ok | warn | stopped against the month's totals. The dollar side only
    counts when every call this month carried a price -- one unpriced call
    and it stops enforcing (cost_complete False) so a budget never bites on a
    number that is known to be short.
    """
    totals = totals or month_totals(model_config)
    tokens_budget = model_config.monthly_token_budget
    cost_budget = model_config.monthly_cost_budget_usd
    fractions: list[Decimal] = []
    tokens_remaining = cost_remaining = None
    if tokens_budget:
        fractions.append(Decimal(totals["tokens"]) / Decimal(tokens_budget))
        tokens_remaining = max(0, tokens_budget - totals["tokens"])
    if cost_budget and totals["cost_complete"]:
        spent = totals["cost_usd"] or Decimal("0")
        fractions.append(spent / Decimal(cost_budget))
        cost_remaining = max(Decimal("0"), Decimal(cost_budget) - spent)
    fraction = max(fractions) if fractions else None
    state = "ok"
    if fraction is not None and fraction >= 1:
        state = "stopped"
    elif fraction is not None and fraction >= WARN_AT:
        state = "warn"
    return {
        "state": state,
        "fraction": float(fraction) if fraction is not None else None,
        "tokens_remaining": tokens_remaining,
        "cost_remaining": cost_remaining,
        "cost_complete": totals["cost_complete"],
        "resets_at": next_month_start(),
    }


def is_model_stopped(model_config) -> bool:
    return budget_state(model_config)["state"] == "stopped"


def stopped_personas(personas) -> list:
    """The personas whose model is stopped this month; one check per model."""
    by_model: dict = {}
    out = []
    for p in personas:
        model = p.model
        if model.id not in by_model:
            by_model[model.id] = is_model_stopped(model)
        if by_model[model.id]:
            out.append(p)
    return out


def evaluate_budget(model_config, topic) -> None:
    """
    After a call: post the 90 % warning and the 100 % stop, each once per
    month, in the topic where it happened. The stop refuses every trigger on
    this model from now on (stopped_personas / is_model_stopped read the live
    totals, so raising the budget lifts it at once).
    """
    from chat import services as chat_svc
    from nucleus.models import ModelConfig

    state = budget_state(model_config)
    if state["state"] == "ok":
        return
    first = month_start().date()
    if state["state"] == "stopped":
        if model_config.budget_stopped_at == first:
            return
        content = (
            f"{model_config.name} has used its monthly budget. Personas on it won't answer "
            f"until {next_month_start():%-d %b} (UTC) or the budget is raised."
        )
        ModelConfig.objects.filter(id=model_config.id).update(budget_stopped_at=first, budget_warned_at=first)
        model_config.budget_stopped_at = model_config.budget_warned_at = first
    else:
        if model_config.budget_warned_at == first:
            return
        content = f"{model_config.name} has used 90% of its monthly budget."
        ModelConfig.objects.filter(id=model_config.id).update(budget_warned_at=first)
        model_config.budget_warned_at = first
    msg = chat_svc.save_system_message(company=model_config.company, project=topic.project, topic=topic, content=content)
    chat_svc.publish(chat_svc.topic_channel(str(topic.id)), {**msg, "type": "message"})


# ── What the app shows ────────────────────────────────────────────────────────

def _totals_out(t: dict) -> dict:
    return {
        "input": t["input"], "output": t["output"], "cache_read": t["cache_read"], "cache_write": t["cache_write"],
        "total": t["tokens"], "requests": t["requests"], "calls": t["calls"],
        "cost_usd": float(t["cost_usd"]) if t["cost_usd"] is not None else None,
        "cost_complete": t["cost_complete"],
    }


def usage_summary(model_config) -> dict:
    month = month_totals(model_config)
    state = budget_state(model_config, month)
    return {
        "month": _totals_out(month),
        "all_time": _totals_out(all_time_totals(model_config)),
        "budget": {
            "tokens": model_config.monthly_token_budget,
            "cost_usd": float(model_config.monthly_cost_budget_usd) if model_config.monthly_cost_budget_usd is not None else None,
            "tokens_remaining": state["tokens_remaining"],
            "cost_remaining": float(state["cost_remaining"]) if state["cost_remaining"] is not None else None,
            "state": state["state"],
            "fraction": state["fraction"],
            "resets_at": state["resets_at"].isoformat(),
        },
    }


# ── Provider balances (OpenRouter is the one provider that reports one) ────────

def fetch_openrouter_key(api_key: str) -> dict:
    r = httpx.get("https://openrouter.ai/api/v1/auth/key", headers={"Authorization": f"Bearer {api_key}"}, timeout=10)
    r.raise_for_status()
    return r.json().get("data") or {}


def provider_remaining(model_config) -> dict | None:
    """OpenRouter's own limit/usage/remaining for this key, cached five minutes; None for every other provider."""
    if model_config.provider != "openai_compatible" or OPENROUTER_HOST not in (model_config.api_base or ""):
        return None
    api_key = model_config.get_api_key()
    if not api_key:
        return None
    key = str(model_config.id)
    now = time.monotonic()
    cached = _provider_cache.get(key)
    if cached and now - cached[0] < PROVIDER_CACHE_SECONDS:
        return cached[1]
    data = fetch_openrouter_key(api_key)
    out = {"limit": data.get("limit"), "usage": data.get("usage"), "remaining": data.get("limit_remaining")}
    _provider_cache[key] = (now, out)
    return out
