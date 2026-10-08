"""
Runbooks (W6): a step of a runbook builds on the step before it. Nucleus
puts the previous reply on the job (TriggerJob.step_context); it joins the
persona's system prompt as its own block after everything else that shapes
this turn (brief, persona prompt, routine), clipped to its head so a long
report cannot crowd out the prompt.
"""
from __future__ import annotations

from apps.core.config import settings
from apps.schemas.trigger import PersonaConfig

STEP_HEADING = "Previous step's output — this step builds on it:"
CLIP_NOTE = "\n[… clipped: the previous step's output was longer]"


def apply_step_context(persona: PersonaConfig, step_context: str) -> PersonaConfig:
    text = step_context.strip()
    if not text:
        return persona
    limit = settings.RUNBOOK_STEP_CONTEXT_MAX
    if len(text) > limit:
        text = text[:limit].rstrip() + CLIP_NOTE
    return persona.model_copy(update={"system_prompt": f"{persona.system_prompt}\n\n{STEP_HEADING}\n{text}"})
