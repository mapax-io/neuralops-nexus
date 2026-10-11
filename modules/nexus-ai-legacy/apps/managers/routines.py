"""
Routines (W4): a team-shared method a persona runs with for ONE reply.

Nucleus names it on the job (routine_id) and the worker fetches it the way it
fetches the persona. Applying it returns a persona copy: the instructions
join the system prompt after the persona's own (the brief is already ahead
of both); allowed_capabilities keeps only the listed tools -- an
intersection, never an addition; a model on the routine replaces the
persona's for the turn.
"""
from __future__ import annotations

from dataclasses import dataclass

from apps.schemas.trigger import ModelConfig, PersonaCapabilities, PersonaConfig

ROUTINE_HEADING = "Routine {title} — follow it for this reply:"

# Capability ids, as tool levels use them, to the PersonaCapabilities field.
BUILT_IN_CAPABILITIES = ("shell", "filesystem", "web_search", "web_fetch", "thinking")


@dataclass(frozen=True)
class RoutineConfig:
    id: str
    name: str
    title: str
    instructions: str
    allowed_capabilities: list[str] | None = None
    model: ModelConfig | None = None


def routine_from(data: dict) -> RoutineConfig:
    """Shape nucleus's internal routine payload."""
    from apps.managers.nucleus_client import model_from
    model_data = data.get("model")
    return RoutineConfig(
        id=data["id"], name=data["name"], title=data.get("title") or data["name"], instructions=data.get("instructions") or "",
        allowed_capabilities=data.get("allowed_capabilities"), model=model_from(model_data) if model_data else None,
    )


def apply_routine(persona: PersonaConfig, routine: RoutineConfig) -> PersonaConfig:
    """The persona as this turn runs it: instructed, narrowed, and on the routine's model when it has one."""
    changes: dict = {"system_prompt": f"{persona.system_prompt}\n\n{ROUTINE_HEADING.format(title=routine.title)}\n{routine.instructions.strip()}"}
    if routine.allowed_capabilities is not None:
        allowed = set(routine.allowed_capabilities)
        kept = {name: getattr(persona.capabilities, name) for name in BUILT_IN_CAPABILITIES if name in allowed}
        changes["capabilities"] = PersonaCapabilities(**kept)
        changes["mcp_servers"] = [s for s in persona.mcp_servers if s.id and f"mcp:{s.id}" in allowed]
    if routine.model is not None:
        changes["model"] = routine.model
    return persona.model_copy(update=changes)
