"""
Turn rules — Layer 6's per-turn transforms, ported from legacy and kept to the
0.8.0 wire contract (both files read 2026-10-14):

Runbooks (W6, legacy apps/managers/runbooks.py): a runbook step builds on the
step before it — nucleus puts the previous reply on the job as
`TriggerJob.step_context`; it joins the prompt as its own block, clipped to
its head so a long report cannot crowd out the prompt.

Preflight (legacy apps/managers/preflight.py): a gated persona proposes before
acting. Nucleus flags the job (`preflight=True`) while no plan is approved;
the ENGINE owns the acts-at-all judgement. A turn that would act runs ONCE
WITH NO CAPABILITY TOOLS and answers as the `preflight` output type; the
approved plan comes back as `approved_plan` and rides as its own PROTECTED
block with the tools restored.

Placement note (deliberate deviation): legacy spliced both blocks into the
system prompt string (plan ahead of it, step context after it). Here each is
its own VOLATILE PromptSection, landing after the stable prefix — the cache
rule (item 15: stable first) wins over legacy's byte order; the headings are
kept verbatim.
"""
from __future__ import annotations

from typing import Sequence

from ai_engine.core.specs import PromptSection, ToolCatalogEntry

STEP_HEADING = "Previous step's output — this step builds on it:"
CLIP_NOTE = "\n[… clipped: the previous step's output was longer]"
PLAN_HEADING = "Approved plan — carry out these steps and nothing beyond them:"

# Sources that change something outside the conversation (legacy
# ACTING_CAPABILITIES, catalog-based here). Reading the web or thinking
# harder needs no one's approval — and no plan.
_ACTING_NATIVES = frozenset({"shell", "filesystem"})


def acts_with_tools(catalog: Sequence[ToolCatalogEntry]) -> bool:
    """Would a normal turn of this persona be able to run a tool that acts?
    Any MCP server counts (legacy rule: persona.mcp_servers truthy), as does
    an acting native capability."""
    return any(
        entry.source_kind == "mcp" or entry.tool_id in _ACTING_NATIVES
        for entry in catalog
    )


def step_context_section(step_context: str | None, limit: int) -> PromptSection | None:
    """The runbook step block (W6), clipped to its head — one volatile section.
    Priority 86: droppable under budget pressure, after the catalog (80)."""
    text = (step_context or "").strip()
    if not text:
        return None
    if len(text) > limit:
        text = text[:limit].rstrip() + CLIP_NOTE
    return PromptSection(kind="step_context", priority=86, stable=False,
                         text=f"{STEP_HEADING}\n{text}")


def approved_plan_section(approved_plan: str | None) -> PromptSection | None:
    """The approved plan block — PROTECTED (priority 91): a plan the person
    approved is never dropped by the BudgetFitter (sections < 90 are)."""
    text = (approved_plan or "").strip()
    if not text:
        return None
    return PromptSection(kind="approved_plan", priority=91, stable=False,
                         text=f"{PLAN_HEADING}\n{text}")
