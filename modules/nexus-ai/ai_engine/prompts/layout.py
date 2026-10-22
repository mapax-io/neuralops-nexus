"""
PromptLayout — the prompt as ordered sections: stable first (cache-friendly),
system prompt once. Layer 0 rule (§1.5): instructions = project brief (if any)
then persona prompt, both stable; history; then the new message as the last
user turn.

Joined with "\n\n", the sections reproduce 0.8.0's composed system prompt
byte for byte (legacy prompt_builder.compose_system_prompt).
"""
from __future__ import annotations

from typing import Sequence

from ai_engine.core.specs import (
    ContextBundle,
    PersonaSpec,
    PromptPlan,
    PromptSection,
    ToolCatalogEntry,
)
from ai_engine.prompts.templates import PromptTemplates


class PromptLayout:
    def __init__(self, templates: PromptTemplates) -> None:
        self._templates = templates

    def build(self, persona: PersonaSpec, bundle: ContextBundle, message: str,
              catalog: Sequence[ToolCatalogEntry] = ()) -> PromptPlan:
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
        if catalog:
            # Item 1: the catalog — one line per ELIGIBLE tool, stable per
            # topic so the cache prefix survives. Full schemas travel only for
            # the loaded set, via the tools parameter, never in this text.
            lines = "\n".join(f"- {e.model_name}: {e.one_line}" for e in catalog)
            # Honesty rule (live finding 2026-10-22: a persona invented date/ls
            # transcripts): tool RESULTS are the only ground truth — appended
            # after the lines so the section still starts with the same stable
            # prefix byte-for-byte.
            sections.append(PromptSection(
                kind="tool_catalog", priority=80, stable=True,
                text="Tools available in this conversation:\n" + lines + (
                    "\nTool results are the only ground truth: never invent, "
                    "embellish or simulate a tool's output. If a call is "
                    "refused, denied or unavailable, say so plainly instead of "
                    "imagining what it would have returned."
                ),
            ))
        return PromptPlan(instructions=tuple(sections), history=bundle.history, message=message)
