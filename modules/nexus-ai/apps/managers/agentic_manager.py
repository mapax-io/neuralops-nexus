"""
Agentic Manager
---------------
Owns the full agent execution loop:
  TriggerJob → Context Manager → Prompt Builder → AgentRunner → SSE events

M7 additions:
  - Resolve output type (explicit → cosine classifier → "text" default)
  - Inject output type system instruction into prompt
  - Parse <<<OUTPUT:type>>> markers from full response
  - Include output_type + render_as in message_done event

This is the entry point called by the /trigger/ router.
The AgentRunner is injected — swap Pydantic AI for LangGraph here.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import AsyncIterator

from apps.interfaces.agent import AgentRunner
from apps.interfaces.embedding import EmbeddingModel
from apps.interfaces.vectorstore import VectorStore, Chunk
from apps.factories.context_source import ContextSourceFactory
from apps.managers.prompt_builder import PromptBuilder
from apps.schemas.trigger import TriggerJob, AgentEvent

log = logging.getLogger(__name__)


class AgenticManager:
    def __init__(
        self,
        runner: AgentRunner,
        embedder: EmbeddingModel,
        store: VectorStore,
    ) -> None:
        self.runner = runner
        self.embedder = embedder
        self.store = store
        self.prompt_builder = PromptBuilder()

    async def run(self, job: TriggerJob) -> AsyncIterator[AgentEvent]:
        """
        Full pipeline: resolve output type → retrieve context → build prompt
                       → run agent → yield events.
        """
        # 1. Resolve output type
        resolved_type = await self._resolve_output_type(job)

        # 2. Get output type spec (system instruction + render_as)
        from apps.output_types import OutputTypeRegistry
        spec = OutputTypeRegistry.get(resolved_type)
        output_instruction = spec.system_instruction if spec else None
        render_as = spec.render_as if spec else "text"

        # 3. Retrieve relevant context chunks
        chunks: list[Chunk] = []
        for source in job.context_sources:
            try:
                plugin = ContextSourceFactory.get(source.type)
                filter_dict = (
                    {"topic_id": source.source_id}
                    if source.type == "chat"
                    else {"source_id": source.source_id}
                )
                source_chunks = await plugin.retrieve(
                    query=job.message,
                    collection_id=source.collection_id,
                    top_k=5,
                    filter=filter_dict,
                )
                chunks.extend(source_chunks)
            except Exception as exc:
                log.warning(
                    "[agentic] context retrieval failed for source %s (%s): %s",
                    source.source_id, source.type, exc,
                )

        # 4. Build the messages array
        messages = self.prompt_builder.build(
            job=job,
            context_chunks=chunks,
            output_type_instruction=output_instruction,
        )

        # 5. Yield message_start immediately
        yield AgentEvent(
            type="message_start",
            id=job.msg_id,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

        # 6. Stream from agent runner (raw — may contain markers)
        full_content: list[str] = []
        async for event in self.runner.run_stream(job, messages):
            if event.type == "message_delta" and event.delta:
                full_content.append(event.delta)
            yield event

        # 7. Parse output markers from the full assembled response
        raw_full = "".join(full_content)
        from apps.output_types.markers import parse_output_markers
        clean_content, marker_type = parse_output_markers(raw_full)

        # Marker type overrides the resolved type if present
        if marker_type and OutputTypeRegistry.get(marker_type):
            # Markers found — use the matched spec's renderer
            final_type = marker_type
            final_spec = OutputTypeRegistry.get(marker_type)
            final_render_as = final_spec.render_as if final_spec else render_as
        else:
            # No markers — the model chose to respond in plain text.
            # Always render as text regardless of the resolved output type,
            # so a conversational reply doesn't end up in a chart/html box.
            final_type = resolved_type
            final_render_as = "text"
            clean_content = raw_full

        # 8. Yield message_done with clean content + type metadata
        yield AgentEvent(
            type="message_done",
            id=job.msg_id,
            content=clean_content,
            output_type=final_type,
            render_as=final_render_as,
        )

    async def _resolve_output_type(self, job: TriggerJob) -> str:
        """
        Resolve the output type for this job.

        Priority:
        1. Explicit type from job (set by nexus-nucleus via @mention)
        2. Cosine similarity classification (when output_type == "auto")
        3. "text" default
        """
        from apps.output_types import OutputTypeRegistry

        explicit = job.output_type

        if explicit and explicit != "auto":
            if OutputTypeRegistry.get(explicit):
                log.debug("[agentic] output type explicit: %s", explicit)
                return explicit
            log.warning("[agentic] unknown explicit output type %r — falling back to auto", explicit)

        # Auto-classify
        try:
            from apps.output_types.classifier import classify_output_type
            detected = await classify_output_type(job.message)
            log.debug("[agentic] output type classified: %s", detected)
            return detected
        except Exception as exc:
            log.warning("[agentic] classifier failed: %s", exc)
            return "text"
