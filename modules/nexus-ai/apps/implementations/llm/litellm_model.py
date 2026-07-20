"""
LiteLLM implementation of LLMModel.
Supports 100+ providers via one unified interface.
Model is resolved from: persona config → settings.LLM_MODEL fallback.
"""
from __future__ import annotations

from typing import AsyncIterator

import litellm

from apps.interfaces.llm import LLMModel
from apps.core.config import settings


class LiteLLMModel(LLMModel):
    def __init__(self, model_id: str | None = None) -> None:
        # model_id from LLMFactory (persona-level override) → global default
        self.model_id = model_id or settings.LLM_MODEL

    async def stream(
        self,
        messages: list[dict],
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> AsyncIterator[str]:
        response = await litellm.acompletion(
            model=self.model_id,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            stream=True,
        )
        async for chunk in response:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta
