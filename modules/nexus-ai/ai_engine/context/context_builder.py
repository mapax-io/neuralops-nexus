"""
ContextBuilder — gather everything a reply needs. Layer 0: history only;
Layer 3 adds retrieval. Knows nothing about pydantic-ai or the web framework.
"""
from __future__ import annotations

from ai_engine.context.history_policy import HistoryPolicy
from ai_engine.core.nucleus_client import NucleusClient
from ai_engine.core.specs import ContextBundle, PersonaSpec
from fastapi_app.contracts.trigger import TriggerJob


class ContextBuilder:
    def __init__(self, nucleus: NucleusClient, policy: HistoryPolicy) -> None:
        self._nucleus = nucleus
        self._policy = policy

    async def gather(self, job: TriggerJob, persona: PersonaSpec) -> ContextBundle:
        rows = await self._nucleus.get_history(
            job.topic_id, limit=self._policy.depth, exclude_message_id=job.user_message_id,
        )
        history = self._policy.select(rows, persona)
        return ContextBundle(history=tuple(history))
