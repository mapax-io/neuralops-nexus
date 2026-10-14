"""
Escalation (items 13 + 46) — the router's hand-over, as verified in trial G
(2026-10-13, pinned 2.55): `Escalate` is a structured OUTPUT TYPE on the
routing run (`output_type=[str, Escalate, ...]`). The model "calling escalate"
is the model calling the `final_result` output tool, which ends the routing
run cleanly with this struct; the deep answer is then a SECOND ordinary
streaming run. No custom plumbing.

This is a pydantic model (framework-facing), so it lives in
pydantic_ai_system/ — never in ai_engine.core.specs (dependency rule 2).
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class Escalate(BaseModel):
    """Hand this question to the persona's deeper model.

    Call this instead of answering whenever the question needs deep reasoning,
    multi-step tool work, or more capability than you have. Fill every field
    from what you already know — the deeper model starts from this note.
    """

    task: str = Field(description="What needs to be done, in one or two sentences.")
    summary: str = Field(default="", description="What is already known or was "
                         "said in the conversation that the deeper model needs.")
    expected_output: str = Field(default="", description="What shape the answer "
                                 "should take (a proof, code, a plan, ...).")
    tool_hints: list[str] = Field(default_factory=list, description="Tool ids "
                                  "from the catalog the deeper model will likely "
                                  "need (e.g. 'filesystem', 'mcp:<id>/<tool>').")


# Appended to the ROUTING run's instructions (stable text — same every turn).
ROUTER_INSTRUCTIONS = (
    "\n\nRouting stage: you are the first, fast pass over this question. "
    "EITHER answer it directly (when it is simple and needs no tools or deep "
    "work) OR hand it over by returning an Escalate — never both, and never "
    "a partial answer followed by a hand-over. When you escalate, fill "
    "tool_hints with the tool ids from the catalog the deeper model will need."
)


def handover_suffix(escalate: Escalate) -> str:
    """Appended to the DEEP run's instructions: the router's distillation.
    The deep run keeps the topic history and the user's own message — this is
    the same persona continuing the same conversation (unlike Layer 6's
    cross-persona Handover, which travels alone)."""
    parts = [f"\n\nA routing stage decided this needs you.\nTask: {escalate.task}"]
    if escalate.summary:
        parts.append(f"Known so far: {escalate.summary}")
    if escalate.expected_output:
        parts.append(f"Expected output: {escalate.expected_output}")
    return "\n".join(parts)
