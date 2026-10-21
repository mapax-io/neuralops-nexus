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
            # 7b (owner's ruling 2026-10-20): the CANDIDATE's own numbers — a
            # fallback or seat with a smaller ceiling generates within it
            # (deepseek-chat's 8K never borrows the primary's 16K). An older
            # nucleus fills these from the persona's legacy values upstream
            # (nucleus_client.model_spec_from), so this is never a behaviour
            # break, only a sharpening.
            model_settings={
                "temperature": spec.temperature,
                "max_tokens": spec.max_output_tokens,  # the OUTPUT cap, never the window
            },
        )
