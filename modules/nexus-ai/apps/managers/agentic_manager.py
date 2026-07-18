"""
Agentic Manager
---------------
Owns the full agent execution loop:
  TriggerJob → Context Manager → Prompt Builder → AgentRunner → SSE events

This is the entry point called by the /trigger/ router.
The AgentRunner is injected — swap Pydantic AI for LangGraph here.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import AsyncIterator

from apps.interfaces.agent import AgentRunner
from apps.interfaces.embedding import EmbeddingModel
from apps.interfaces.vectorstore import VectorStore
from apps.managers.context_manager import ContextManager
from apps.managers.prompt_builder import PromptBuilder
from apps.schemas.trigger import TriggerJob, AgentEvent


class AgenticManager:
    def __init__(
        self,
        runner: AgentRunner,
        embedder: EmbeddingModel,
        store: VectorStore,
    ) -> None:
        self.runner = runner
        self.context_manager = ContextManager(embedder=embedder, store=store)
        self.prompt_builder = PromptBuilder()

    async def run(self, job: TriggerJob) -> AsyncIterator[AgentEvent]:
        """
        Full pipeline: retrieve context → build prompt → run agent → yield events.
        """
        # 1. Retrieve relevant context chunks
        chunks = await self.context_manager.retrieve(
            message=job.message,
            history=job.history,
            context_sources=job.context_sources,
        )

        # 2. Build the messages array (system + context + history + message)
        messages = self.prompt_builder.build(job=job, context_chunks=chunks)

        # 3. Yield message_start immediately so the client knows streaming began
        yield AgentEvent(
            type="message_start",
            id=job.msg_id,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

        # 4. Stream from agent runner — pass messages directly (no model_copy tricks)
        full_content: list[str] = []
        async for event in self.runner.run_stream(job, messages):
            if event.type == "message_delta" and event.delta:
                full_content.append(event.delta)
            yield event

        # 5. Yield message_done with full content for nexus-nucleus to save to DB
        yield AgentEvent(
            type="message_done",
            id=job.msg_id,
            content="".join(full_content),
        )
