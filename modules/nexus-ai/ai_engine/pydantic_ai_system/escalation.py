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

from typing import Sequence

from pydantic import BaseModel, Field

from ai_engine.core.specs import ModelSpec


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
    # Smart router (ruled 2026-10-20): the bench pick. The instructions list
    # the deeper models with their strengths; the router copies one NAME here.
    target_model: str = Field(default="", description="Which of the listed "
                              "deeper models should take this — copy its name "
                              "exactly. Leave blank when no list was given.")


# Appended to the ROUTING run's instructions (stable text — same every turn).
ROUTER_INSTRUCTIONS = (
    "\n\nRouting stage: you are the first, fast pass over this question. "
    "EITHER answer it directly (when it is simple and needs no tools or deep "
    "work) OR hand it over by returning an Escalate — never both, and never "
    "a partial answer followed by a hand-over. When you escalate, fill "
    "tool_hints with the tool ids from the catalog the deeper model will need."
)


def router_instructions(bench: Sequence[ModelSpec]) -> str:
    """The routing-stage instructions. With a BENCH of two or more deeper
    models (smart router, ruled 2026-10-20) they are listed with each one's
    strengths note (ModelConfig.routing_notes), so the router can NAME its
    pick in Escalate.target_model. One or zero deep models → nothing to
    choose → the plain instructions."""
    if len(bench) < 2:
        return ROUTER_INSTRUCTIONS
    lines = "\n".join(
        f"- {spec.name}: {spec.routing_notes}" if spec.routing_notes else f"- {spec.name}"
        for spec in bench
    )
    return ROUTER_INSTRUCTIONS + (
        "\n\nDeeper models on the bench — when you escalate, weigh their pros "
        "and cons below and set target_model to the NAME of the best fit "
        "(the first is the default when none stands out):\n" + lines
    )


def pick_deep_model(escalate: Escalate, bench: Sequence[ModelSpec]) -> ModelSpec | None:
    """The bench model the router named; an invalid, missing or blank pick
    falls back to the bench's FIRST (the default). None only when the bench
    is empty — the caller then keeps the reply on STANDARD."""
    want = (escalate.target_model or "").strip().lower()
    if want:
        for spec in bench:
            if want in (spec.name.lower(), spec.model_id.lower()):
                return spec
    return bench[0] if bench else None


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
