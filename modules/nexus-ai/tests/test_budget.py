"""
Layer 2, item 16 — context budget, selection and the tool loop
(docs/NEXUS-AI-REVAMP.md §4.1, settled; built 2026-10-13).

Unit tests of BudgetFitter (pure — the estimator is injected) plus acceptance
through the running service: a small window trims history before the run, and
persona.max_steps finally caps the tool loop.
"""
from __future__ import annotations

import pytest

from ai_engine.context.budget import Budget, BudgetFitter, budget_for
from ai_engine.core.specs import HistoryMessage, ModelRole, ModelSpec, PromptPlan, PromptSection
from conftest import openai_model
from fake_nucleus import make_persona

pytestmark = pytest.mark.asyncio


def _words(text: str) -> int:
    return len(text.split())


def _plan(history_texts: list[str]) -> PromptPlan:
    return PromptPlan(
        instructions=(
            PromptSection(kind="persona_prompt", priority=90, stable=True, text="be brief"),
            PromptSection(kind="tool_catalog", priority=80, stable=True, text="- a tool"),
        ),
        history=tuple(HistoryMessage(role="user", author=None, text=t) for t in history_texts),
        message="current question",
    )


def test_b_budget_formula_keeps_the_two_numbers_apart():
    """Item 16 — input_budget = context_window − max_output_tokens − headroom.
    The window comes from the MODEL, the output cap from the PERSONA — two
    fields, never one (the 0.8.0 defect §4.1 exists to bury); target and
    trigger are percentages of the budget, target < trigger."""
    spec = ModelSpec(role=ModelRole.STANDARD, config_id="m", name="m", provider="openai",
                     model_id="m", base_url=None, api_key=None, context_window=100_000,
                     supports_tools=True, supports_streaming=True, supports_vision=False)
    budget = budget_for(spec, loop_headroom=8_000, target_pct=70, trigger_pct=90,
                        max_output_tokens=4_096)
    assert budget.input_budget == 100_000 - 4_096 - 8_000
    assert budget.target == budget.input_budget * 70 // 100
    assert budget.trigger == budget.input_budget * 90 // 100
    assert budget.target < budget.trigger < budget.input_budget


def test_b_fitter_under_target_is_untouched():
    """Item 16 — a plan already under the target passes through byte-identical.
    Selection never rewrites what fits: same sections, same history, same
    message object — the cache prefix is not disturbed for nothing."""
    fitter = BudgetFitter(_words)
    plan = _plan(["one two", "three four"])
    out = fitter.fit(plan, Budget(input_budget=1000, target=700, trigger=900))
    assert out is plan


def test_b_fitter_drops_oldest_history_first():
    """Item 16 — over the target, OLD history goes first, oldest message first.
    The newest history survives longest; the current message and the persona
    prompt are never candidates (§4.1's protected list)."""
    fitter = BudgetFitter(_words)
    plan = _plan(["oldest " * 50, "middle " * 50, "newest newest"])
    # fixed cost: 2+2 (sections) + 2 (message) = 6; history: 50+50+2
    out = fitter.fit(plan, Budget(input_budget=100, target=60, trigger=90))
    texts = [m.text for m in out.history]
    assert all("oldest" not in t for t in texts)
    assert any("newest" in t for t in texts)
    assert out.message == "current question"
    assert any(s.kind == "persona_prompt" for s in out.instructions)


def test_b_fitter_drops_catalog_before_touching_protected():
    """Item 16 — after history, droppable sections go by ascending priority.
    With all history gone and still over target, the tool_catalog (priority 80)
    is dropped; the persona prompt (90) and the message never are — protected
    content over the target is sent anyway (the escape valve is indexing,
    items 33/34, not truncation)."""
    fitter = BudgetFitter(_words)
    big_catalog = PromptSection(kind="tool_catalog", priority=80, stable=True,
                                text="tool " * 100)
    plan = PromptPlan(
        instructions=(
            PromptSection(kind="persona_prompt", priority=90, stable=True, text="be brief"),
            big_catalog,
        ),
        history=(),
        message="current question",
    )
    out = fitter.fit(plan, Budget(input_budget=50, target=20, trigger=45))
    kinds = [s.kind for s in out.instructions]
    assert "tool_catalog" not in kinds and "persona_prompt" in kinds
    assert out.message == "current question"


# ── acceptance: through the running service ─────────────────────────────────────

async def test_b_small_window_trims_history_before_the_run(harness):
    """Item 16 — selection happens BEFORE the run: a small window drops old history.
    The model's context_window is tiny; ten long history rows are sent by
    nucleus, but the provider request carries only the newest few — and the
    persona prompt and the current message are still there."""
    model = openai_model(harness, context_window=10_500)
    harness.nucleus.persona = make_persona(model, max_tokens=100)
    long_text = "word " * 600  # ≈900 estimated tokens per row
    harness.nucleus.history = [
        {"id": str(i), "sender_type": "human", "sender_name": "u",
         "content": f"[{i}] {long_text}", "render_as": "text", "output_type": "text",
         "stopped": False, "sequence": i}
        for i in range(10)
    ]
    import os
    os.environ["BUDGET_LOOP_HEADROOM"] = "2000"
    try:
        events = await harness.trigger()
    finally:
        os.environ.pop("BUDGET_LOOP_HEADROOM", None)
    assert [e for e in events if e["type"] == "message_done"]
    body = harness.provider.requests[-1]
    user_msgs = [m for m in body["messages"] if m.get("role") == "user"]
    history_sent = [m for m in user_msgs if "word word" in m.get("content", "")]
    assert 0 < len(history_sent) < 10          # trimmed, not emptied
    assert "[9]" in history_sent[-1]["content"]  # the newest survived
    assert user_msgs[-1]["content"] == "current question"
    sys_msgs = [m for m in body["messages"] if m.get("role") == "system"]
    assert any("PERSONA-PROMPT-MARKER" in m["content"] for m in sys_msgs)


async def test_b_max_steps_caps_the_tool_loop(harness, tmp_path):
    """Item 16 — persona.max_steps finally caps agent rounds (UsageLimits).
    The scripted model calls a tool on EVERY request, forever; with
    max_steps=3 the run is stopped by the limit — one clean message_error,
    no infinite loop, and the spent calls are still billed."""
    (tmp_path / "data.txt").write_text("x")
    persona = make_persona(
        openai_model(harness), max_steps=3,
        capabilities=[{"id": "cap1", "name": "defaults",
                       "capability_config": {"filesystem": {"root_dir": str(tmp_path)}}}],
    )
    harness.nucleus.persona = persona
    harness.provider.script.steps = [  # last step repeats forever → endless loop
        {"kind": "tool_call", "call_id": "call_loop", "name": "read_file",
         "args": {"path": "data.txt"}},
    ]
    events = await harness.trigger()
    types = [e["type"] for e in events]
    assert types[-1] == "message_error"
    assert "message_done" not in types
    assert len(harness.provider.requests) <= 4  # capped, not infinite
    records = await harness.wait_for_usage(1)
    assert records  # the spent rounds still billed
