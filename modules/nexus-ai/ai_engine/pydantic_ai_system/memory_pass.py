"""
The memory pass — item 27 (Layer 4, decision 8): after a reply that ran tools,
ONE cheap model call decides what the run's tool outputs deserve: `raw` (exact
data worth keeping — the text itself, chunked), `summary` (a verbal note WITH
the exact key figures and provenance), or `skip` (re-runnable / worthless).

Seat chain: UTILITY → ROUTER → STANDARD (owner: "there must be some utility,
otherwise router or standard will be utility"). The pass runs AFTER
message_done — memory housekeeping never delays the reply — and its failure is
logged, never surfaced (memory is a bonus). Billed kind="memory" under the
seat's role.

Ephemeral data the USER will need as a durable file still belongs in the data
MCP (decision 12); this pass preserves what the MODEL may need to remember.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.run import AgentRunResultEvent

from ai_engine.core.specs import ModelRole, ModelSpec, PersonaSpec, UsageRecord, VectorItem
from ai_engine.pydantic_ai_system.model_factory import ModelFactory
from ai_engine.pydantic_ai_system.tools.approval_policy import args_preview
from ai_engine.vector_db.chunking import chunk_text
from fastapi_app.contracts.trigger import TriggerJob

log = logging.getLogger(__name__)

PREVIEW_CHARS = 1500   # per output, in the pass's prompt
RAW_CAP_CHARS = 4000   # per output, stored when the ruling is `raw`

MEMORY_INSTRUCTIONS = (
    "You are the memory keeper for an AI assistant. A reply just finished; below "
    "are the tool outputs it saw. For EACH output decide what deserves project "
    "memory:\n"
    "- raw: exact data worth keeping word for word (figures, records, listings "
    "from remote or ephemeral sources that may vanish or change)\n"
    "- summary: the gist is enough — write it yourself, INCLUDING the exact key "
    "figures and names; one short paragraph\n"
    "- skip: re-runnable locally (project files, directory listings), transient, "
    "or worthless\n"
    "Rules of thumb: local project files are re-readable → usually skip; "
    "remote/ephemeral sources → usually save. You may override either way when "
    "it is clearly right (an expensive local scan, a trivial remote ping).\n"
    "Answer one ruling per output, by index."
)


class MemoryRuling(BaseModel):
    index: int
    action: Literal["raw", "summary", "skip"] = "skip"
    summary: str = ""


class MemoryRulings(BaseModel):
    rulings: list[MemoryRuling] = Field(default_factory=list)


def memory_seat(persona: PersonaSpec) -> tuple[ModelSpec, ModelRole]:
    """UTILITY → ROUTER → STANDARD (decision 8's chain)."""
    if persona.utility_model is not None:
        return persona.utility_model, ModelRole.STANDARD
    router = persona.model_for_or_none(ModelRole.ROUTER)
    if router is not None:
        return router, ModelRole.ROUTER
    return persona.model_for(ModelRole.STANDARD), ModelRole.STANDARD


def _prompt(outputs: list[dict]) -> str:
    lines = []
    for n, out in enumerate(outputs):
        content = out.get("content") or ""
        clipped = content[:PREVIEW_CHARS] + ("…" if len(content) > PREVIEW_CHARS else "")
        lines.append(f"[{n}] tool={out.get('tool')} args={args_preview(out.get('args') or {})}"
                     f" size={len(content)} chars\n{clipped}")
    return "Tool outputs of the finished reply:\n\n" + "\n\n".join(lines)


def _items(job: TriggerJob, outputs: list[dict], rulings: MemoryRulings) -> list[VectorItem]:
    now = datetime.now(timezone.utc).isoformat()
    items: list[VectorItem] = []
    for ruling in rulings.rulings:
        if not (0 <= ruling.index < len(outputs)) or ruling.action == "skip":
            continue
        out = outputs[ruling.index]
        label = f"{out.get('tool')} {args_preview(out.get('args') or {})}".strip()
        base = dict(kind="tool_result", label=label, source=f"toolres:{job.msg_id}",
                    topic_id=job.topic_id, created_at=now)
        if ruling.action == "summary" and ruling.summary.strip():
            items.append(VectorItem(id=f"{job.msg_id}:tr{ruling.index}",
                                    text=ruling.summary.strip(), **base))
        elif ruling.action == "raw":
            content = (out.get("content") or "")[:RAW_CAP_CHARS]
            for n, chunk in enumerate(chunk_text(content)):
                items.append(VectorItem(id=f"{job.msg_id}:tr{ruling.index}:{n}",
                                        text=chunk, **base))
    return items


async def run_memory_pass(job: TriggerJob, persona: PersonaSpec,
                          outputs: list[dict], store) -> tuple[UsageRecord | None, int]:
    """One structured-output call + the index writes. Returns (usage record,
    rows saved); raises nothing — the caller logs."""
    import asyncio

    # The project's index is created by nucleus's embed calls with the
    # project's OWN embedder (decision 3) — the pass never guesses one. No
    # index yet = nothing to join: skip before any model call (zero cost).
    if not await asyncio.to_thread(store.has_index, job.project_id):
        log.debug("[memory] no index for project %s — pass skipped", job.project_id)
        return None, 0

    spec, role = memory_seat(persona)
    agent = Agent(model=ModelFactory().build(spec), output_type=MemoryRulings,
                  instructions=MEMORY_INSTRUCTIONS,
                  model_settings={"temperature": 0.0, "max_tokens": 2000})
    # streamed like every other call in the engine — the one road every
    # provider (and the test fake) actually serves
    result = None
    async with agent.run_stream_events(_prompt(outputs)) as run:
        async for event in run:
            if isinstance(event, AgentRunResultEvent):
                result = event.result
    if result is None:
        return None, 0
    rulings = result.output if isinstance(result.output, MemoryRulings) else MemoryRulings()
    items = _items(job, outputs, rulings)
    if items:
        await asyncio.to_thread(store.index, job.company_id, job.project_id, items)
    usage = result.usage
    record = UsageRecord(
        company_id=job.company_id, project_id=job.project_id, topic_id=job.topic_id,
        persona_id=job.persona_id, user_id=job.user_id, message_id=job.msg_id,
        job_id=job.job_id, kind="memory",
        model_config_id=spec.config_id, provider=spec.provider, model_id=spec.model_id,
        role=role.value, provider_response_id=None,
        input_tokens=usage.input_tokens or 0,
        uncached_input_tokens=max(0, (usage.input_tokens or 0) - (usage.cache_read_tokens or 0)),
        cache_read_tokens=usage.cache_read_tokens or 0,
        cache_write_5m_tokens=0, cache_write_1h_tokens=0,
        output_tokens=usage.output_tokens or 0, reasoning_tokens=0,
        finish_reason="stop", estimated=False,
        called_at=datetime.now(timezone.utc),
    )
    return record, len(items)
