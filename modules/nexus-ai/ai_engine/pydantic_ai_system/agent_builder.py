"""
AgentBuilder — builds the pydantic-ai agent for a persona and model role.

The system prompt goes through `instructions=`, NEVER `system_prompt=`:
pydantic-ai drops system_prompt whenever message history is passed (trial A6,
verified again on the pinned 2.55.0). Temperature and the output limit travel
in model_settings — the two Appendix A drops the rebuild must not inherit.
Layer 1 adds tools here.
"""
from __future__ import annotations

from pydantic_ai import Agent
from pydantic_ai.tools import DeferredToolRequests

from ai_engine.core.specs import ModelRole, ModelSpec, PersonaSpec
from ai_engine.pydantic_ai_system.escalation import Escalate
from ai_engine.pydantic_ai_system.model_factory import ModelFactory


class AgentBuilder:
    def __init__(self, models: ModelFactory) -> None:
        self._models = models

    def build(self, persona: PersonaSpec, role: ModelRole, instructions: str,
              escalate: bool = False, spec: ModelSpec | None = None) -> Agent:
        # spec override (item 12): a fallback CANDIDATE is built for the same
        # seat with a different model — the retry loop in ReplyGenerator.
        spec = spec or persona.model_for(role)
        # Item 2: DeferredToolRequests in the output union is REQUIRED for an
        # approval pause to surface (trial D mark); a plain text reply still
        # comes out as str. Item 13/46: Escalate in the union gives the
        # routing run its hand-over (trial G) — only on runs that may escalate.
        output_type: list = [str, DeferredToolRequests]
        if escalate:
            output_type.append(Escalate)
        return Agent(
            model=self._models.build(spec),
            instructions=instructions,
            output_type=output_type,
            model_settings={
                "temperature": persona.temperature,
                "max_tokens": persona.max_output_tokens,  # the OUTPUT cap, never the window
            },
        )
