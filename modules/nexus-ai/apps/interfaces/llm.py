"""
LLMModel interface — every LLM backend implements this.
Swap LiteLLM for any other provider by adding a new implementation.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator


class LLMModel(ABC):
    """Abstract LLM model — streaming only."""

    @abstractmethod
    async def stream(
        self,
        messages: list[dict],
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> AsyncIterator[str]:
        """
        Yields text tokens one at a time as they arrive from the model.
        messages: OpenAI-format list of {role, content} dicts.
        """
        ...
