"""
LiteLLM-based AgentRunner implementation.

Uses litellm.acompletion() directly for all providers — simpler and more
reliable than pydantic-ai model wrappers for the streaming use case.

Model routing via model_id prefix (LiteLLM convention):
    "openai/gpt-4o-mini"                    → OpenAI
    "anthropic/claude-haiku-4-5-20251001"   → Anthropic
    "azure/gpt-4"                            → Azure OpenAI
    "ollama/llama3"                          → Ollama (provider=local)

For M8 MCP integration: wrap with pydantic-ai Agent + mcp_servers here only.
"""
from __future__ import annotations

import logging
import time
from typing import AsyncIterator

import httpx
import litellm

from apps.interfaces.agent import AgentRunner
from apps.schemas.trigger import TriggerJob, AgentEvent, ModelConfig
from apps.core.config import settings

# Suppress litellm's verbose logging
litellm.suppress_debug_info = True

log = logging.getLogger(__name__)


class PydanticAIRunner(AgentRunner):
    """
    Streams LLM responses via LiteLLM.
    Receives the fully-assembled messages list from PromptBuilder and
    yields message_delta events.
    """

    async def run_stream(
        self,
        job: TriggerJob,
        messages: list[dict],
    ) -> AsyncIterator[AgentEvent]:
        model_config = job.persona.model
        kwargs = _build_litellm_kwargs(model_config, messages)

        full_response = ""
        prompt_tokens = 0
        completion_tokens = 0
        status = "success"
        error_msg = None
        t0 = time.monotonic()

        try:
            response = await litellm.acompletion(**kwargs)
            async for chunk in response:
                delta = chunk.choices[0].delta.content or ""
                if delta:
                    full_response += delta
                    yield AgentEvent(
                        type="message_delta",
                        id=job.msg_id,
                        delta=delta,
                    )
                # Accumulate usage from the final chunk (some providers send it there)
                if hasattr(chunk, "usage") and chunk.usage:
                    prompt_tokens = getattr(chunk.usage, "prompt_tokens", 0) or 0
                    completion_tokens = getattr(chunk.usage, "completion_tokens", 0) or 0
        except Exception as exc:
            status = "error"
            error_msg = str(exc)
            log.error("[runner] litellm error for job %s: %s", job.job_id, exc)
            raise
        finally:
            latency_ms = int((time.monotonic() - t0) * 1000)
            await _post_ai_request_log(
                job=job,
                messages=messages,
                response=full_response,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                latency_ms=latency_ms,
                status=status,
                error=error_msg,
            )


async def _post_ai_request_log(
    *,
    job: TriggerJob,
    messages: list[dict],
    response: str,
    prompt_tokens: int,
    completion_tokens: int,
    latency_ms: int,
    status: str,
    error: str | None,
) -> None:
    """Fire-and-forget POST to nucleus internal API to persist the AI request log."""
    url = f"{settings.NEXUS_NUCLEUS_URL}/api/v1/internal/ai-request-logs/"
    payload = {
        "job_id": job.job_id,
        "msg_id": job.msg_id,
        "persona_id": str(job.persona.id) if job.persona else None,
        "model_id": job.persona.model.model_id if job.persona else "",
        "provider": job.persona.model.provider if job.persona else "",
        "prompt": messages,
        "response": response,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "latency_ms": latency_ms,
        "status": status,
        "error": error,
    }
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(url, json=payload)
    except Exception as exc:
        log.warning("[runner] failed to post AI request log: %s", exc)


def _build_litellm_kwargs(model_config: ModelConfig, messages: list[dict]) -> dict:
    """Build kwargs dict for litellm.acompletion()."""
    kwargs: dict = {
        "model": model_config.model_id,
        "messages": messages,
        "stream": True,
        "max_tokens": model_config.max_tokens,
        "temperature": model_config.temperature,
    }

    if model_config.provider == "local":
        # Local runtime (Ollama, llama.cpp, LM Studio) — OpenAI-compatible API
        kwargs["api_base"] = f"{settings.OLLAMA_BASE_URL}/v1"
        kwargs["api_key"] = "local"
    elif model_config.api_key:
        kwargs["api_key"] = model_config.api_key

    return kwargs
