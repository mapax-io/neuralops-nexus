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

from typing import AsyncIterator

import litellm

from apps.interfaces.agent import AgentRunner
from apps.schemas.trigger import TriggerJob, AgentEvent, ModelConfig
from apps.core.config import settings

# Suppress litellm's verbose logging
litellm.suppress_debug_info = True


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

        try:
            response = await litellm.acompletion(**kwargs)
            async for chunk in response:
                delta = chunk.choices[0].delta.content or ""
                if delta:
                    yield AgentEvent(
                        type="message_delta",
                        id=job.msg_id,
                        delta=delta,
                    )
        except Exception as exc:
            import logging
            logging.getLogger(__name__).error(
                "[runner] litellm error for job %s: %s", job.job_id, exc
            )
            raise


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
