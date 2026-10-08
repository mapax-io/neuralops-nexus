"""
W8 Nudge: what the caller adds while the reply runs reaches the model with
its next tool result, and the stream says it was taken.
"""
import pytest

from apps.managers.nudges import NUDGE_NOTE, NudgeGate
from apps.schemas.trigger import AgentEventType


def gate(texts):
    emitted = []

    async def poll():
        if isinstance(texts, Exception):
            raise texts
        out = list(texts)
        texts.clear()
        return out
    g = NudgeGate("m1", poll=poll, emit=emitted.append)
    return g, emitted


@pytest.mark.asyncio
async def test_a_waiting_nudge_joins_the_next_tool_result_and_is_announced():
    g, emitted = gate(["also the 2023 figure"])
    out = await g.after_tool_execute(None, call=None, tool_def=None, args={}, result="rows: 3")
    assert out == "rows: 3" + NUDGE_NOTE.format(text="also the 2023 figure")
    assert [(e.type, e.nudge) for e in emitted] == [(AgentEventType.NUDGE_TAKEN, "also the 2023 figure")]
    assert g.taken == ["also the 2023 figure"]
    # Taken once: the next call sees nothing more.
    assert await g.after_tool_execute(None, call=None, tool_def=None, args={}, result="ok") == "ok"


@pytest.mark.asyncio
async def test_no_nudge_and_a_failed_poll_leave_the_result_alone():
    g, emitted = gate([])
    assert await g.after_tool_execute(None, call=None, tool_def=None, args={}, result={"a": 1}) == {"a": 1}
    g, emitted = gate(RuntimeError("nucleus away"))
    assert await g.after_tool_execute(None, call=None, tool_def=None, args={}, result="ok") == "ok"
    assert emitted == []


@pytest.mark.asyncio
async def test_a_structured_result_is_rendered_so_the_note_still_reaches_the_model():
    g, _ = gate(["cite it"])
    out = await g.after_tool_execute(None, call=None, tool_def=None, args={}, result={"rows": 3})
    assert out.startswith("{'rows': 3}") and "cite it" in out


def test_an_interactive_run_carries_the_gate(monkeypatch):
    from apps.implementations.agents.pydantic_ai_runner import PydanticAIRunner
    from apps.tests.test_recall import persona
    seen = {}

    class FakeAgent:
        def __init__(self, **kw):
            seen.update(kw)
    monkeypatch.setattr("apps.implementations.agents.pydantic_ai_runner.Agent", FakeAgent)
    monkeypatch.setattr(PydanticAIRunner, "_resolve_capabilities", staticmethod(lambda *a: []))
    monkeypatch.setattr(PydanticAIRunner, "build_model", staticmethod(lambda c: "model"))
    g = NudgeGate("m1", poll=None, emit=lambda e: None)
    PydanticAIRunner.build_agent(persona(), None, nudges=g)
    assert g in seen["capabilities"]
    PydanticAIRunner.build_agent(persona(), None)
    assert not any(isinstance(c, NudgeGate) for c in seen["capabilities"])
