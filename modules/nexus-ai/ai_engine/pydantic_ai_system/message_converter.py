"""
MessageConverter — prompt plan → pydantic-ai messages and the single
instructions string. Decides nothing: selection happened in HistoryPolicy,
ordering in PromptLayout.
"""
from __future__ import annotations

from typing import Sequence

from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    UserPromptPart,
)

from ai_engine.core.specs import HistoryMessage, PromptPlan


class MessageConverter:
    def to_messages(self, history: Sequence[HistoryMessage]) -> list[ModelMessage]:
        messages: list[ModelMessage] = []
        for msg in history:
            if msg.role == "user":
                messages.append(ModelRequest(parts=[UserPromptPart(content=msg.text)]))
            else:
                messages.append(ModelResponse(parts=[TextPart(content=msg.text)]))
        return messages

    def instructions(self, plan: PromptPlan) -> str:
        """Sections joined with a blank line, stable first (cache order),
        original order kept within each group. The system prompt text ends up
        in the request exactly once (T2)."""
        stable = [s.text for s in plan.instructions if s.stable]
        volatile = [s.text for s in plan.instructions if not s.stable]
        return "\n\n".join(stable + volatile)
