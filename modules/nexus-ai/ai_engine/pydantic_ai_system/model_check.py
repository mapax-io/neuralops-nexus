"""
Model check (item 40, Layer 2) — one tiny call to a model with the given key,
so nucleus can verify a model before saving it (the Register / Edit dialogs).

The model is built by the SAME ModelFactory a persona run uses, and the call
streams the same way a reply does — so "the check passed" means "a persona on
this model will run", not "some other code path worked".

The answer is a plain dict (0.8.0's shape, kept): ok with the latency, or not
ok with the raw error (for nucleus to word, never shown raw), the HTTP status
when there is one, and an error_code — "unsupported_provider" when this worker
cannot run the provider at all, "model_failure" when the model could not be
used (bad key, no credit, unknown model, provider down), "timeout", else
"error".
"""
from __future__ import annotations

import asyncio
import logging
import time

from pydantic_ai import Agent
from pydantic_ai.exceptions import ModelAPIError, ModelHTTPError

from ai_engine.core.specs import ModelRole, ModelSpec
from ai_engine.pydantic_ai_system.model_factory import ModelFactory

log = logging.getLogger(__name__)

CHECK_PROMPT = "Reply with the single word OK."
SUPPORTED_PROVIDERS = {"openai", "anthropic", "google", "ollama", "openai_compatible", "deepseek"}


def _spec_for_check(provider: str, model_id: str, api_key: str | None,
                    api_base: str | None) -> ModelSpec:
    return ModelSpec(
        role=ModelRole.STANDARD, config_id="model-check", name=model_id,
        provider=provider, model_id=model_id, base_url=api_base, api_key=api_key,
        context_window=8192, supports_tools=True, supports_streaming=True,
        supports_vision=False,
    )


def _is_model_failure(exc: Exception) -> bool:
    """Bad key, no credit, unknown model, provider down — the model could not
    be used, as opposed to a bug on our side."""
    if isinstance(exc, (ModelHTTPError, ModelAPIError, ConnectionError, OSError)):
        return True
    return getattr(exc, "status_code", None) is not None


async def check_model(provider: str, model_id: str, api_key: str | None,
                      api_base: str | None, timeout: float = 20.0) -> dict:
    if provider.lower() not in SUPPORTED_PROVIDERS:
        return {"ok": False, "error_code": "unsupported_provider",
                "error": f"provider '{provider}' is not supported by this worker"}
    started = time.monotonic()
    try:
        spec = _spec_for_check(provider, model_id, api_key, api_base)
        agent = Agent(model=ModelFactory().build(spec))

        async def _one_call() -> None:
            async with agent.run_stream_events(
                CHECK_PROMPT, model_settings={"max_tokens": 5},
            ) as run:
                async for _ in run:
                    pass

        await asyncio.wait_for(_one_call(), timeout)
    except (asyncio.TimeoutError, TimeoutError):
        return {"ok": False, "error_code": "timeout",
                "error": f"the model did not answer within {timeout:.0f}s (timed out)"}
    except Exception as exc:  # noqa: BLE001 — every failure becomes a worded answer
        status = getattr(exc, "status_code", None)
        log.info("[model_check] %s:%s failed: %s %s", provider, model_id,
                 type(exc).__name__, status or "")
        return {
            "ok": False,
            "error_code": "model_failure" if _is_model_failure(exc) else "error",
            "error": str(exc),
            "status_code": status if isinstance(status, int) else None,
        }
    return {"ok": True, "latency_ms": int((time.monotonic() - started) * 1000)}
