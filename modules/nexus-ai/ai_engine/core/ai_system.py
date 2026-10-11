"""
AISystem (the interface), AISystemFactory, PydanticAISystem.

One interface for now (O4): respond(job) → stream of AgentEvent. A later
system (e.g. Claude Agent SDK, item 18) implements the same interface and the
factory chooses.

PydanticAISystem runs the steps of one reply (§1.5 Layer 0 sequence) and
records usage on EVERY ending — done, stop, failure:
  - done   → record usage, then message_done with the full text and usage
  - cancel → the run is cancelled by the disconnect; usage is recorded
             (estimated) under a shield; no event can be sent
  - error  → usage recorded, the exception propagates and EventStream turns
             it into exactly one message_error
message_done is yielded on the normal path, never from a finally block —
yielding while a generator is being closed raises RuntimeError.
record_usage failure is logged and never turns a good reply into an error.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import AsyncIterator, Protocol

from ai_engine.context.context_builder import ContextBuilder
from ai_engine.context.history_policy import HistoryPolicy
from ai_engine.core.config import EngineSettings
from ai_engine.core.nucleus_client import NucleusClient
from ai_engine.core.specs import ModelRole, PersonaSpec, ReplyRequest
from ai_engine.prompts.layout import PromptLayout
from ai_engine.prompts.templates import PromptTemplates
from ai_engine.pydantic_ai_system.agent_builder import AgentBuilder
from ai_engine.pydantic_ai_system.message_converter import MessageConverter
from ai_engine.pydantic_ai_system.model_factory import ModelFactory
from ai_engine.pydantic_ai_system.reply_generator import ReplyGenerator
from ai_engine.pydantic_ai_system.usage_reader import UsageReader
from fastapi_app.contracts.trigger import AgentEvent, AgentEventType, TriggerJob

log = logging.getLogger(__name__)


class AISystem(Protocol):
    def respond(self, job: TriggerJob) -> AsyncIterator[AgentEvent]: ...


class AISystemFactory:
    @staticmethod
    def create(kind: str) -> AISystem:
        """Return the AI system to use — "pydantic_ai" only in Layer 0.
        Builds a fresh object graph per call: a run holds per-run state."""
        if kind != "pydantic_ai":
            raise ValueError(f"unknown AI system kind: {kind!r}")
        settings = EngineSettings()
        nucleus = NucleusClient(
            settings.nucleus_url, settings.internal_key,
            timeout_seconds=settings.nucleus_timeout_seconds,
        )
        return PydanticAISystem(
            nucleus=nucleus,
            context=ContextBuilder(nucleus, HistoryPolicy(settings.history_depth)),
            layout=PromptLayout(PromptTemplates()),
            generator=ReplyGenerator(AgentBuilder(ModelFactory()), MessageConverter(), UsageReader()),
        )


class PydanticAISystem:
    def __init__(self, nucleus: NucleusClient, context: ContextBuilder,
                 layout: PromptLayout, generator: ReplyGenerator) -> None:
        self._nucleus = nucleus
        self._context = context
        self._layout = layout
        self._generator = generator

    async def respond(self, job: TriggerJob) -> AsyncIterator[AgentEvent]:
        yield AgentEvent(
            type=AgentEventType.START,
            id=job.msg_id,
            persona_id=job.persona_id,
            created_at=_now(),
        )
        persona: PersonaSpec | None = None
        try:
            persona = await self._nucleus.get_persona(job.persona_id, job.company_id, job.project_id)
            bundle = await self._context.gather(job, persona)
            plan = self._layout.build(persona, bundle, job.message)
            request = ReplyRequest(job=job, persona=persona, role=ModelRole.STANDARD, plan=plan)
            async for event in self._generator.generate(request):
                yield event
        except asyncio.CancelledError:
            # The person (or nucleus) stopped the run: no event can be sent any
            # more, but the partial usage must still land. Shield the write so
            # the cancellation doesn't take it down with the run.
            await self._record_usage(shielded=True)
            raise
        except Exception:
            await self._record_usage()
            raise  # EventStream turns this into exactly one message_error
        else:
            await self._record_usage()
            records = self._generator.usage_records()
            last = records[-1] if records else None
            yield AgentEvent(
                type=AgentEventType.END,
                id=job.msg_id,
                persona_id=persona.id,
                persona_name=persona.name,
                created_at=_now(),
                content=self._generator.full_text(),
                output_type="text",
                render_as="text",
                answered_by_model=None,
                prompt_tokens=last.input_tokens if last else None,
                output_tokens=last.output_tokens if last else None,
                context_window=persona.model_for(ModelRole.STANDARD).context_window,
            )

    async def _record_usage(self, shielded: bool = False) -> None:
        """Logged on failure, never raised — a good reply stays good (T15)."""
        records = self._generator.usage_records()
        if not records:
            return
        try:
            call = self._nucleus.record_usage(records)
            if shielded:
                await asyncio.shield(asyncio.ensure_future(call))
            else:
                await call
        except asyncio.CancelledError:
            # cancelled again while recording — the shielded task finishes on its own
            if not shielded:
                raise
        except Exception:
            log.exception("record_usage failed for job %s", records[0].job_id)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
