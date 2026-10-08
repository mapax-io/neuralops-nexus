"""
Model check: one tiny call to a model with the given key, so a model can be
verified before it is saved (the Register / Edit model dialogs). The model is
built exactly as a persona run builds it, so "the check passed" means "a
persona on this model will run".

The answer is a plain dict: ok with the latency, or not ok with the raw error
(for nucleus to word, never shown raw), the HTTP status when there is one,
and an error_code -- "unsupported_provider" when this worker cannot run the
provider at all, "model_failure" when the model could not be used (bad key,
no credit, unknown model, provider down), "timeout", else "error".
"""
from __future__ import annotations

import asyncio
import logging
import time

from pydantic_ai import Agent

from apps.core.config import settings
from apps.managers.fallbacks import is_model_failure
from apps.schemas.trigger import ModelConfig

log = logging.getLogger(__name__)

CHECK_PROMPT = "Reply with the single word OK."


async def check_model(config: ModelConfig, timeout: float | None = None) -> dict:
    from apps.implementations.agents.pydantic_ai_runner import PydanticAIRunner

    if config.provider.lower() not in PydanticAIRunner._MODEL_REGISTRY:
        return {"ok": False, "error_code": "unsupported_provider", "error": f"provider '{config.provider}' is not supported by this worker"}
    timeout = timeout or settings.MODEL_CHECK_TIMEOUT_SECONDS
    started = time.monotonic()
    try:
        agent = Agent(model=PydanticAIRunner.build_model(config))
        await asyncio.wait_for(agent.run(CHECK_PROMPT, model_settings={"max_tokens": 5}), timeout)
    except asyncio.TimeoutError:
        return {"ok": False, "error_code": "timeout", "error": f"the model did not answer within {timeout:.0f}s (timed out)"}
    except Exception as exc:
        status = getattr(exc, "status_code", None)
        log.info("[model_check] %s:%s failed: %s %s", config.provider, config.model_id, type(exc).__name__, status or "")
        return {
            "ok": False,
            "error_code": "model_failure" if is_model_failure(exc) else "error",
            "error": str(exc),
            "status_code": status if isinstance(status, int) else None,
        }
    return {"ok": True, "latency_ms": int((time.monotonic() - started) * 1000)}
