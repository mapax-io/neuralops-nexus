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
    """Hand this question onward instead of answering it yourself.

    Call this whenever the question needs tools, real work, or more capability
    than you have. Fill every field from what you already know — the model
    that takes over starts from this note.
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
    # Three-way routing (ruled 2026-10-21, after "2+2" and an ordinary
    # explainer both landed on the expensive bench): 'standard' sends the
    # work to the persona's everyday model with its full tools — the right
    # lane for most real questions; 'deep' is for the genuinely hard ones.
    lane: str = Field(default="deep", description="'standard' to hand this "
                      "to the persona's everyday model (ordinary questions "
                      "and work — the usual choice), or 'deep' for the "
                      "deeper model (genuinely hard reasoning or long-form "
                      "work only).")


# Appended to the ROUTING run's instructions (stable text — same every turn).
ROUTER_INSTRUCTIONS = (
    "\n\nRouting stage: you are the first, fast pass over this question, and "
    "you have three choices — pick exactly one, never answer AND escalate. "
    "(1) Answer it yourself ONLY when it is trivial: greetings, thanks, quick "
    "facts, simple arithmetic, one-line clarifications — anything whose "
    "correct answer fits in a sentence or two. You have no tools, so answer "
    "only what you can answer correctly from what you see. HARD CEILING: if "
    "a proper answer would take more than a couple of sentences, it is not "
    "yours — escalate it. NEVER answer yourself a request for code, a proof, "
    "an analysis, a summary of a text, a document, a plan, a translation of "
    "more than a line, or anything multi-step — however confident you feel, "
    "those always escalate. When unsure, escalate with lane='standard'. "
    "(2) Return an Escalate with lane='standard' for ordinary questions and "
    "work — the persona's everyday model takes it with its full tools. This "
    "is the usual choice for anything real. "
    "(3) Return an Escalate with lane='deep' ONLY when it genuinely needs "
    "deep reasoning or long-form work — a proof, hard code, intricate "
    "analysis — the deeper model is the expensive one, so reserve it for "
    "the hard problems. "
    "When you escalate, fill tool_hints with the tool ids from the catalog "
    "the next model will need."
    # Three-way ruled 2026-10-21 after live tests: gpt-4o-mini escalated
    # "what's 2+2?" and an ordinary explainer straight to the expensive
    # bench; the standard seat never spoke. Lane 'standard' gives the
    # cheap→medium→expensive ladder the seats were bought for.
    # HARD CEILING added 2026-10-23 after the owner's live routing pass:
    # the keep-it bias overcorrected — gpt-4o-mini answered a math proof,
    # a parser-with-tests ask and a 3-point philosophy summary INLINE
    # (nine router-only usage rows in a row, no standard/deep row ever).
    # The ceiling names the never-inline classes and defaults doubt to
    # lane='standard', the cheap mistake.
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
        "\n\nDeeper models on the bench — when you escalate with lane='deep', "
        "weigh their pros and cons below and set target_model to the NAME of "
        "the best fit (the first is the default when none stands out):\n" + lines
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
