"""
ReplyGenerator — produce one reply with pydantic-ai: build the agent, convert
messages, stream, collect usage. One instance serves one run (the factory
builds a fresh graph per request).

usage_records() is available after ANY ending — done, cancel, or error:
  - normal end: one record per ModelResponse in the run (one in Layer 0),
    read by UsageReader (which flags the cut-stream shapes estimated);
  - cancelled: one estimated record from whatever was received;
  - error: one estimated record, so a model 500 still bills its input (T9).
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse, UserPromptPart
from pydantic_ai.run import AgentRunResultEvent

from ai_engine.core.specs import ModelSpec, ReplyRequest, UsageRecord
from ai_engine.pydantic_ai_system.agent_builder import AgentBuilder
from ai_engine.pydantic_ai_system.event_mapper import EventMapper
from ai_engine.pydantic_ai_system.message_converter import MessageConverter
from ai_engine.pydantic_ai_system.usage_reader import UsageReader
from fastapi_app.contracts.trigger import AgentEvent


class ReplyGenerator:
    def __init__(self, agents: AgentBuilder, converter: MessageConverter, usage: UsageReader) -> None:
        self._agents = agents
        self._converter = converter
        self._usage = usage
        self._records: list[UsageRecord] = []
        self._mapper: EventMapper | None = None

    async def generate(self, request: ReplyRequest):
        spec = request.persona.model_for(request.role)
        instructions = self._converter.instructions(request.plan)
        agent = self._agents.build(request.persona, request.role, instructions)
        history = self._converter.to_messages(request.plan.history)
        request_messages: list[ModelMessage] = history + [
            ModelRequest(parts=[UserPromptPart(content=request.plan.message)])
        ]
        mapper = EventMapper(msg_id=request.job.msg_id, persona=request.persona)
        self._mapper = mapper
        self._records = []
        base = _base_record(request, spec)
        result = None
        try:
            async with agent.run_stream_events(
                request.plan.message, message_history=history,
            ) as run:
                async for event in run:
                    if isinstance(event, AgentRunResultEvent):
                        result = event.result
                    for out in mapper.map(event):
                        yield out
            for out in mapper.flush():
                yield out
        except asyncio.CancelledError:
            self._records = [self._usage.read(None, request_messages, mapper.text(), True, base)]
            raise
        except Exception:
            self._records = [self._usage.read(None, request_messages, mapper.text(), False, base)]
            raise

        responses = (
            [m for m in result.new_messages() if isinstance(m, ModelResponse)] if result else []
        )
        if responses:
            self._records = [
                self._usage.read(r, request_messages, mapper.text(), False, base) for r in responses
            ]
        else:  # the stream ended without a result — estimated, like a cut
            self._records = [self._usage.read(None, request_messages, mapper.text(), False, base)]

    def usage_records(self) -> list[UsageRecord]:
        """One per model call; available after any ending."""
        return list(self._records)

    def full_text(self) -> str:
        return self._mapper.text() if self._mapper else ""


def _base_record(request: ReplyRequest, spec: ModelSpec) -> UsageRecord:
    job = request.job
    return UsageRecord(
        company_id=job.company_id,
        project_id=job.project_id,
        topic_id=job.topic_id,
        persona_id=job.persona_id,
        user_id=job.user_id,
        message_id=job.msg_id,
        job_id=job.job_id,
        kind="chat_reply",
        model_config_id=spec.config_id,
        provider=spec.provider,
        model_id=spec.model_id,
        role=request.role.value,
        provider_response_id=None,
        input_tokens=0,
        uncached_input_tokens=0,
        cache_read_tokens=0,
        cache_write_5m_tokens=0,
        cache_write_1h_tokens=0,
        output_tokens=0,
        reasoning_tokens=0,
        finish_reason=None,
        estimated=False,
        called_at=datetime.now(timezone.utc),
    )
