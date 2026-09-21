"""
Preflight: a persona that proposes before acting.

Nucleus flags the job (`preflight=True`) when the persona is gated and no plan
has been approved yet; the worker owns the judgement of whether this run
would act at all -- nucleus never reads a capability config. A run that
would act gets one turn with no tools and the `preflight` output type; an
approved plan comes back as `approved_plan` and rides ahead of the persona
prompt with the tools restored.
"""
from apps.schemas.trigger import PersonaCapabilities, PersonaConfig, TriggerJob

PLAN_HEADING = "Approved plan — carry out these steps and nothing beyond them:"

# Capabilities that change something outside the conversation. Reading the
# web or thinking harder needs no one's approval.
ACTING_CAPABILITIES = ("shell", "filesystem")


def acts_with_tools(persona: PersonaConfig) -> bool:
    """Would a normal turn of this persona be able to run a tool that acts?"""
    if persona.mcp_servers:
        return True
    return any(getattr(persona.capabilities, name) is not None for name in ACTING_CAPABILITIES)


def plan_turn(job: TriggerJob, persona: PersonaConfig) -> tuple[PersonaConfig, str]:
    """
    The persona to run this turn with, and the output type to resolve it as.
    A preflight turn strips the tools and answers as a plan; an approved plan
    is composed ahead of the prompt; anything else passes through untouched.
    """
    if job.approved_plan:
        return persona.model_copy(update={"system_prompt": f"{PLAN_HEADING}\n{job.approved_plan.strip()}\n\n{persona.system_prompt}"}), job.output_type
    if job.preflight and acts_with_tools(persona):
        return persona.model_copy(update={"mcp_servers": [], "capabilities": PersonaCapabilities()}), "preflight"
    return persona, job.output_type
