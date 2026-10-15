"""
Layer 6 — runbook step context (W6) and preflight (plan before acting)
(docs/NEXUS-AI-REVAMP.md Layer 6 decisions 3 + 4; legacy runbooks.py and
preflight.py read 2026-10-14; built 2026-10-14).

Runbooks: nucleus sequences the steps; the engine's half is the step_context
block — the previous step's output joins the prompt, clipped to its head.
Preflight: a gated persona's turn that WOULD act runs once with no capability
tools and answers as the preflight type; the approved plan rides protected
with the tools restored; a persona that cannot act passes through untouched.
"""
from __future__ import annotations

import json
import os

import pytest

from conftest import openai_model
from fake_nucleus import make_persona

pytestmark = pytest.mark.asyncio

PLAN_JSON = json.dumps({"title": "Write the file", "steps": [
    {"n": 1, "action": "create out.txt with the summary"},
    {"n": 2, "action": "stop"},
]})


def _by_type(events, kind):
    return [e for e in events if e["type"] == kind]


def _fs_persona(harness, tmp_path) -> dict:
    return make_persona(
        openai_model(harness),
        capabilities=[{"id": "cap1", "name": "defaults",
                       "capability_config": {"filesystem": {"root_dir": str(tmp_path)}}}],
    )


async def test_w1_step_context_joins_the_prompt_clipped(harness):
    """W6 — the previous step's output reaches the prompt, head only.
    A job with step_context and a small RUNBOOK_STEP_CONTEXT_MAX: the request
    carries the legacy heading and the text's HEAD; the tail past the limit is
    gone, replaced by the clip note — a long report cannot crowd out the
    prompt (legacy runbooks.py behaviour, kept verbatim)."""
    step = "DECISION-ALPHA was chosen for the schema. " + ("filler " * 40) + "TAIL-MARKER"
    os.environ["RUNBOOK_STEP_CONTEXT_MAX"] = "120"
    try:
        harness.provider.script.text = "Building on the last step."
        events = await harness.trigger(harness.job(step_context=step))
    finally:
        del os.environ["RUNBOOK_STEP_CONTEXT_MAX"]
    assert _by_type(events, "message_done")
    sent = json.dumps(harness.provider.requests[-1])
    assert "this step builds on it" in sent
    assert "DECISION-ALPHA" in sent
    assert "TAIL-MARKER" not in sent  # clipped to the head
    assert "clipped: the previous step" in sent


async def test_p1_preflight_turn_strips_tools_and_answers_as_a_plan(harness, tmp_path):
    """Preflight — a gated persona that WOULD act proposes first, toolless.
    preflight=true on a filesystem persona: the request carries NO capability
    tools (only item 5's ask_user) and no catalog section; the prompt carries
    the preflight contract; the marked reply lands as output_type=preflight."""
    harness.nucleus.persona = _fs_persona(harness, tmp_path)
    harness.provider.script.text = f"<<<OUTPUT:preflight>>>\n{PLAN_JSON}\n<<<END_OUTPUT>>>"
    events = await harness.trigger(harness.job(preflight=True))
    [done] = _by_type(events, "message_done")
    assert done["output_type"] == "preflight" and done["render_as"] == "preflight"
    assert json.loads(done["content"])["steps"]
    body = harness.provider.requests[-1]
    names = [t["function"]["name"] for t in body.get("tools", [])]
    assert names == ["ask_user"], f"capability tools leaked into the plan turn: {names}"
    sent = json.dumps(body)
    assert "<<<OUTPUT:preflight>>>" in sent
    assert "Tools available" not in sent


async def test_p2_approved_plan_restores_tools_and_rides_protected(harness, tmp_path):
    """Preflight — the approved plan comes back as its own block, tools on.
    approved_plan on the same persona: the capability schemas are BACK in the
    request, the prompt carries the legacy plan heading with the plan text,
    and no preflight contract rides — the turn is an ordinary acting turn."""
    harness.nucleus.persona = _fs_persona(harness, tmp_path)
    harness.provider.script.text = "Carrying out step 1."
    events = await harness.trigger(harness.job(
        preflight=True, approved_plan="1. Create out.txt\n2. Stop"))
    [done] = _by_type(events, "message_done")
    assert done["output_type"] == "text"
    body = harness.provider.requests[-1]
    names = [t["function"]["name"] for t in body.get("tools", [])]
    assert "write_file" in names  # the tools are restored
    sent = json.dumps(body)
    assert "carry out these steps and nothing beyond them" in sent
    assert "Create out.txt" in sent
    assert "<<<OUTPUT:preflight>>>" not in sent


async def test_p3_preflight_on_a_toolless_persona_passes_through(harness):
    """Preflight — a persona that cannot act has nothing to propose.
    preflight=true on a toolless persona: acts_with_tools is false, so the
    turn passes through untouched — no preflight contract, a plain text reply
    (legacy plan_turn's third branch, kept)."""
    harness.provider.script.text = "Just answering normally."
    events = await harness.trigger(harness.job(preflight=True))
    [done] = _by_type(events, "message_done")
    assert done["output_type"] == "text"
    assert done["content"].strip() == "Just answering normally."
    assert "<<<OUTPUT:preflight>>>" not in json.dumps(harness.provider.requests[-1])
