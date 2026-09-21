"""
What a persona's tool calls and usage look like on the event stream.

The runner used to emit only tool_call_start, so nucleus and the app could say
"Searching the web…" and nothing more: no end, no duration, no result, no
error. tool_call_end closes each call; usage rides the PERSIST event to the
manager, which puts prompt/output tokens and the model's context window on
message_done.
"""
import asyncio
import time
from contextlib import asynccontextmanager

import pytest
from pydantic_ai.messages import (
    FunctionToolCallEvent, FunctionToolResultEvent, PartStartEvent, RetryPromptPart, TextPart, ToolCallPart, ToolReturnPart,
)
from pydantic_ai.usage import RunUsage

from apps.implementations.agents.pydantic_ai_runner import PydanticAIRunner
from apps.implementations.agents.tool_events import TOOL_PREVIEW_CHARS, execute_mcp_tool, tool_end_event
from apps.managers import agentic_manager
from apps.managers.agentic_manager import NewImprovedAgenticManager
from apps.schemas.trigger import AgentEvent, AgentEventType
from apps.tests.test_output_type_resolution import job, persona


# ── the event itself ─────────────────────────────────────────────────────────
def test_tool_end_event_carries_name_outcome_duration_and_a_clipped_preview():
    started = time.monotonic() - 0.25
    ev = tool_end_event("m1", "web_search", ok=True, started_at=started, content="x" * 2000)
    assert ev.type == AgentEventType.TOOL_CALL_END and ev.id == "m1"
    assert ev.tool_result.name == "web_search" and ev.tool_result.ok is True
    assert 200 <= ev.tool_result.duration_ms < 5000
    assert len(ev.tool_result.preview) == TOOL_PREVIEW_CHARS and ev.tool_result.error is None


def test_a_failed_tool_call_says_so_and_keeps_the_reason_short():
    ev = tool_end_event("m1", "shell", ok=False, started_at=time.monotonic(), content=None, error="boom " * 200)
    assert ev.tool_result.ok is False and ev.tool_result.preview is None
    assert len(ev.tool_result.error) <= 300


# ── the pydantic-ai runner ───────────────────────────────────────────────────
class _FakeStream:
    """What agent.run_stream_events() hands back: events, then usage and messages."""

    def __init__(self, events, usage):
        self._events = events
        self.usage = usage  # a property on the real AgentRunEvents, never a method

    def __aiter__(self):
        async def gen():
            for e in self._events:
                await asyncio.sleep(0)
                yield e
        return gen()

    def new_messages(self):
        return []


class _FakeAgent:
    def __init__(self, events, usage):
        self._events, self._usage = events, usage

    @asynccontextmanager
    async def run_stream_events(self, message_history):
        yield _FakeStream(self._events, self._usage)


def collect(agen):
    async def run():
        return [e async for e in agen]
    return asyncio.run(run())


def test_pydantic_runner_closes_each_tool_call_and_reports_usage(monkeypatch):
    call = ToolCallPart(tool_name="web_search", args={"q": "gdp"}, tool_call_id="c1")
    failing = ToolCallPart(tool_name="shell", args={"cmd": "ls"}, tool_call_id="c2")
    events = [
        PartStartEvent(index=0, part=TextPart(content="Let me look. ")),
        PartStartEvent(index=1, part=ToolCallPart(tool_name="web_search", args="", tool_call_id="c1")),  # name known, args still streaming
        FunctionToolCallEvent(part=call),
        FunctionToolResultEvent(part=ToolReturnPart(tool_name="web_search", content="Canada GDP is …", tool_call_id="c1")),
        PartStartEvent(index=2, part=ToolCallPart(tool_name="shell", args="", tool_call_id="c2")),
        FunctionToolCallEvent(part=failing),
        FunctionToolResultEvent(part=RetryPromptPart(content="command not allowed", tool_name="shell", tool_call_id="c2")),
        PartStartEvent(index=3, part=TextPart(content="Done.")),
    ]
    monkeypatch.setattr(PydanticAIRunner, "build_agent", staticmethod(lambda p: _FakeAgent(events, RunUsage(input_tokens=1200, output_tokens=40))))
    out = collect(PydanticAIRunner().run_stream(job(), [], persona()))

    kinds = [e.type for e in out]
    starts = [e for e in out if e.type == AgentEventType.TOOL_CALL_START]
    assert [(e.tool_call.name, e.tool_call.args) for e in starts] == [("web_search", {"q": "gdp"}), ("shell", {"cmd": "ls"})]
    ends = [e for e in out if e.type == AgentEventType.TOOL_CALL_END]
    assert [(e.tool_result.name, e.tool_result.ok) for e in ends] == [("web_search", True), ("shell", False)]
    assert ends[0].tool_result.preview == "Canada GDP is …" and ends[0].tool_result.duration_ms >= 0
    assert "not allowed" in ends[1].tool_result.error
    # the end event follows its start, before the next text
    assert kinds.index(AgentEventType.TOOL_CALL_END) > kinds.index(AgentEventType.TOOL_CALL_START)
    persist = next(e for e in out if e.type == AgentEventType.PERSIST)
    assert persist.metadata["usage"] == {"prompt_tokens": 1200, "output_tokens": 40}


# ── the LiteLLM MCP loop's one tool call ─────────────────────────────────────
class _Item:
    def __init__(self, text):
        self.text = text


class _FakeClient:
    def __init__(self, result=None, error=None):
        self._result, self._error = result, error

    async def call_tool(self, name, args):
        if self._error:
            raise self._error
        return self._result


class _Result:
    def __init__(self, items, is_error=False):
        self.content, self.is_error = items, is_error


def test_execute_mcp_tool_returns_text_and_whether_it_worked():
    ok_client = _FakeClient(_Result([_Item("row 1"), _Item("row 2")]))
    assert asyncio.run(execute_mcp_tool(ok_client, "query", {})) == ("row 1\nrow 2", True)
    err_client = _FakeClient(_Result([_Item("permission denied")], is_error=True))
    content, ok = asyncio.run(execute_mcp_tool(err_client, "query", {}))
    assert ok is False and "permission denied" in content
    content, ok = asyncio.run(execute_mcp_tool(_FakeClient(error=RuntimeError("socket closed")), "query", {}))
    assert ok is False and "socket closed" in content
    content, ok = asyncio.run(execute_mcp_tool(None, "missing", {}))
    assert ok is False and "not found" in content


# ── the manager puts usage on message_done ───────────────────────────────────
class _FakeRunner:
    async def run_stream(self, job, messages, persona, tools=None):
        yield AgentEvent(type=AgentEventType.DELTA, id=job.msg_id, delta="Hello")
        yield AgentEvent(type=AgentEventType.PERSIST, id=job.msg_id, metadata={"internal_model_state": [], "usage": {"prompt_tokens": 900, "output_tokens": 12}})


@pytest.mark.asyncio
async def test_message_done_carries_usage_and_the_models_context_window(monkeypatch):
    async def fake_persona(_): return persona()
    async def fake_history(**_): return []
    async def fake_resolve(_): return "text", None
    monkeypatch.setattr(agentic_manager.nucleus_client, "resolve_persona", fake_persona)
    monkeypatch.setattr(agentic_manager.nucleus_client, "fetch_history", fake_history)
    monkeypatch.setattr(agentic_manager, "resolve_output_spec", fake_resolve)
    monkeypatch.setattr(agentic_manager, "context_window_for", lambda model: 200_000)
    manager = NewImprovedAgenticManager(runner=_FakeRunner(), embedder=None, store=None)
    events = [e async for e in manager.run(job())]
    done = next(e for e in events if e.type == AgentEventType.END)
    assert (done.prompt_tokens, done.output_tokens, done.context_window) == (900, 12, 200_000)
    assert done.content == "Hello"
