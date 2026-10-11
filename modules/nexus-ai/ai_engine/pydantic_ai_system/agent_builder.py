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

from ai_engine.core.specs import ModelRole, PersonaSpec
from ai_engine.pydantic_ai_system.model_factory import ModelFactory


class AgentBuilder:
    def __init__(self, models: ModelFactory) -> None:
        self._models = models

    def build(self, persona: PersonaSpec, role: ModelRole, instructions: str) -> Agent:
        spec = persona.model_for(role)
        return Agent(
            model=self._models.build(spec),
            instructions=instructions,
            model_settings={
                "temperature": persona.temperature,
                "max_tokens": persona.max_output_tokens,  # the OUTPUT cap, never the window
            },
        )
