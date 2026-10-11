"""
PromptLayout — the prompt as ordered sections: stable first (cache-friendly),
system prompt once. Layer 0 rule (§1.5): instructions = project brief (if any)
then persona prompt, both stable; history; then the new message as the last
user turn.

Joined with "\n\n", the sections reproduce 0.8.0's composed system prompt
byte for byte (legacy prompt_builder.compose_system_prompt).
"""
from __future__ import annotations

from ai_engine.core.specs import ContextBundle, PersonaSpec, PromptPlan, PromptSection
from ai_engine.prompts.templates import PromptTemplates


class PromptLayout:
    def __init__(self, templates: PromptTemplates) -> None:
        self._templates = templates

    def build(self, persona: PersonaSpec, bundle: ContextBundle, message: str) -> PromptPlan:
        sections: list[PromptSection] = []
        brief = (persona.project_brief or "").strip()
        if brief:
            sections.append(PromptSection(
                kind="project_brief", priority=100, stable=True,
                text=self._templates.render("project_brief.j2", {"brief": brief}),
            ))
        sections.append(PromptSection(
            kind="persona_prompt", priority=90, stable=True,
            text=persona.system_prompt,
        ))
        return PromptPlan(instructions=tuple(sections), history=bundle.history, message=message)
