"""
ReplyGenerator — produce one reply with pydantic-ai: build the agent, convert
messages, stream, collect usage. One instance serves one run (the factory
builds a fresh graph per request).

usage_records() is available after ANY ending — done, pause, cancel, or error:
  - normal end: one record per ModelResponse in the run,
    read by UsageReader (which flags the cut-stream shapes estimated);
  - paused (item 2): same — the paused call's usage is real (trial D5/E2);
  - cancelled: one estimated record from whatever was received;
  - error: one estimated record, so a model 500 still bills its input (T9).

Item 2: a run that ends in DeferredToolRequests sets pause_info() — the caller
(PydanticAISystem) saves it to nucleus and closes with message_paused. A
resume (TriggerJob.resume) re-enters with the stored messages as history and
the decisions as DeferredToolResults — no new user prompt.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from pydantic_ai.messages import (
    ModelMessage,
    ModelMessagesTypeAdapter,
    ModelRequest,
    ModelResponse,
    UserPromptPart,
)
from pydantic_ai.run import AgentRunResultEvent
from pydantic_ai.tools import DeferredToolRequests, DeferredToolResults, ToolApproved, ToolDenied

from ai_engine.core.specs import ModelSpec, PauseInfo, PendingApproval, ReplyRequest, UsageRecord
from ai_engine.pydantic_ai_system.agent_builder import AgentBuilder
from ai_engine.pydantic_ai_system.event_mapper import EventMapper
from ai_engine.pydantic_ai_system.message_converter import MessageConverter
from ai_engine.pydantic_ai_system.tools.approval_gate import ApprovalGate
from ai_engine.pydantic_ai_system.tools.approval_policy import DENIED, args_preview
from ai_engine.pydantic_ai_system.usage_reader import UsageReader
from fastapi_app.contracts.trigger import AgentEvent, ResumeBlock


class ReplyGenerator:
    def __init__(self, agents: AgentBuilder, converter: MessageConverter, usage: UsageReader) -> None:
        self._agents = agents
        self._converter = converter
        self._usage = usage
        self._records: list[UsageRecord] = []
        self._mapper: EventMapper | None = None
        self._pause: PauseInfo | None = None

    async def generate(self, request: ReplyRequest, capabilities: list | None = None,
                       resume: ResumeBlock | None = None, catalog_hash: str = ""):
        """capabilities: harness/pydantic-ai capability objects from
        ToolsetBuilder (Layer 1); None/empty keeps the Layer 0 toolless path.
        resume: the pause state + decisions (item 2) — the run continues
        instead of starting from the new message."""
        spec = request.persona.model_for(request.role)
        instructions = self._converter.instructions(request.plan)
        agent = self._agents.build(request.persona, request.role, instructions)

        if resume is not None:
            history = list(ModelMessagesTypeAdapter.validate_json(resume.state))
            prompt = None
            deferred = _deferred_results(resume)
        else:
            history = self._converter.to_messages(request.plan.history)
            prompt = request.plan.message
            deferred = None
        request_messages: list[ModelMessage] = list(history)
        if prompt is not None:
            request_messages.append(ModelRequest(parts=[UserPromptPart(content=prompt)]))

        gate = next((c for c in capabilities or [] if isinstance(c, ApprovalGate)), None)
        mapper = EventMapper(
            msg_id=request.job.msg_id, persona=request.persona,
            tool_capability_ids=gate.tool_capability_ids if gate else None,
        )
        self._mapper = mapper
        self._records = []
        self._pause = None
        base = _base_record(request, spec)
        result = None
        try:
            async with agent.run_stream_events(
                prompt, message_history=history,
                capabilities=capabilities or None,
                deferred_tool_results=deferred,
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

        # Item 2: a run that produced DeferredToolRequests is PAUSED, not done.
        output = result.output if result else None
        if isinstance(output, DeferredToolRequests):
            names = gate.tool_capability_ids if gate else {}
            self._pause = PauseInfo(
                state=ModelMessagesTypeAdapter.dump_json(result.all_messages()).decode(),
                pending=tuple(
                    PendingApproval(
                        call_id=call.tool_call_id,
                        tool=call.tool_name,
                        capability_id=names.get(call.tool_name, ""),
                        args_preview=args_preview(call.args),
                    )
                    for call in output.approvals
                ),
                catalog_hash=catalog_hash,
            )

    def usage_records(self) -> list[UsageRecord]:
        """One per model call; available after any ending."""
        return list(self._records)

    def full_text(self) -> str:
        return self._mapper.text() if self._mapper else ""

    def pause_info(self) -> PauseInfo | None:
        """Set when the run paused on approvals (item 2); None otherwise."""
        return self._pause


def _deferred_results(resume: ResumeBlock) -> DeferredToolResults:
    approvals: dict = {}
    for call_id, decision in resume.approvals.items():
        if decision.decision == "allow":
            approvals[call_id] = ToolApproved()
        else:
            approvals[call_id] = ToolDenied(decision.reason or DENIED)
    return DeferredToolResults(approvals=approvals)


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
