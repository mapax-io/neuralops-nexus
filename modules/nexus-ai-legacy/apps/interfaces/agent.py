"""
AgentRunner interface — every agent framework implements this.
Swap Pydantic AI for LangGraph by adding a new implementation.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator, TYPE_CHECKING, Sequence

if TYPE_CHECKING:
    from apps.schemas.trigger import (
        TriggerJob,
        AgentEvent,
        PersonaConfig,
        TriggerSwarmJob,
    )


class AgentRunner(ABC):
    """
    Abstract agent runner.
    Receives the job, the resolved persona config, and the fully-assembled
    messages list from PromptBuilder, and yields SSE events back.
    Messages are passed separately so the runner never needs to know about
    context retrieval or prompt assembly — it only calls the model.
    """

    @abstractmethod
    def run_stream(
        self,
        job: TriggerJob | TriggerSwarmJob,
        messages: Sequence,
        persona: PersonaConfig,
        tools: list[dict] | None = None,
    ) -> AsyncIterator[AgentEvent]:
        """
        Run the agent loop for this job.
        persona: resolved by nucleus_client.resolve_persona() in
            AgenticManager.run() -- job itself only carries persona_id (#131).
        messages: fully-assembled OpenAI-format list from PromptBuilder.
        Yields AgentEvent objects (message_delta).
        message_start and message_done are emitted by AgenticManager.
        """
        ...
