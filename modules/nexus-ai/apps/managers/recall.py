"""
Recall (W5), the remember pass: after a reply, the persona's utility model
reads the exchange and proposes what is worth keeping for the project --
decisions, facts, preferences -- as short entries. Nucleus stores them
(deduplicated, capped) and the reply says how many were kept.

Never in the way: a failure here is logged and the reply is unaffected.
"""
from __future__ import annotations

import asyncio
import logging

from pydantic import BaseModel, Field
from pydantic_ai import Agent

from apps.core.config import settings
from apps.managers import nucleus_client
from apps.schemas.trigger import PersonaConfig, TriggerJob

log = logging.getLogger(__name__)

RECALL_KINDS = ("decision", "fact", "preference")

REMEMBER_INSTRUCTIONS = """You keep a project's shared memory for a team of people and AI teammates.
Read one exchange -- a person's message and the reply -- and pick out only what will still matter later:
- decision: something the team decided or agreed on
- fact: a durable fact about the project, its systems, its people or its rules
- preference: how a person or the team wants things done
Write each entry as one plain sentence (at most 300 characters) that stands on its own without the conversation.
Do NOT record greetings, questions, tentative ideas, the reply's reasoning, anything already obvious, or anything sensitive such as credentials.
Most exchanges contain nothing worth keeping: then return an empty list. Never more than five entries."""


class RememberEntry(BaseModel):
    kind: str = Field(description="decision | fact | preference")
    text: str = Field(description="One plain sentence, at most 300 characters")


class RememberOutput(BaseModel):
    entries: list[RememberEntry] = Field(default_factory=list)


def project_id_of(job: TriggerJob) -> str | None:
    """The project the run belongs to, as the recall context source names it; None when recall is off for this run."""
    return next((s.source_id for s in job.context_sources if s.type == "recall"), None)


async def propose_entries(persona: PersonaConfig, user_message: str, reply: str) -> list[dict]:
    """What the utility model thinks is worth keeping from this exchange -- validated shapes only."""
    model = nucleus_client.utility_model_for(persona)
    from apps.implementations.agents.pydantic_ai_runner import PydanticAIRunner
    agent = Agent(model=PydanticAIRunner.build_model(model), instructions=REMEMBER_INSTRUCTIONS, output_type=RememberOutput)
    prompt = f"Person:\n{user_message.strip()[:4000]}\n\nReply from {persona.name}:\n{reply.strip()[:6000]}"
    result = await asyncio.wait_for(agent.run(prompt, model_settings={"max_tokens": 400}), settings.RECALL_REMEMBER_TIMEOUT_SECONDS)
    entries = []
    for entry in result.output.entries[:5]:
        kind, text = (entry.kind or "").strip().lower(), " ".join((entry.text or "").split())
        if kind in RECALL_KINDS and text:
            entries.append({"kind": kind, "text": text[:500]})
    return entries


async def remember(job: TriggerJob, persona: PersonaConfig, reply: str) -> int:
    """The whole pass: propose, record with nucleus, return how many were kept. 0 on any failure."""
    project_id = project_id_of(job)
    if not project_id or not persona.recall_enabled or not reply.strip():
        return 0
    try:
        entries = await propose_entries(persona, job.message, reply)
        if not entries:
            return 0
        return await nucleus_client.record_recall(project_id, persona.id, job.msg_id, entries)
    except Exception as exc:  # noqa: BLE001 -- the reply is done; memory is best effort
        log.warning("[recall] remember pass failed for %s: %s: %s", job.msg_id, type(exc).__name__, exc)
        return 0
