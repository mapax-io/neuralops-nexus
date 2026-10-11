"""
W16 Tool approvals: per persona, each tool carries a level Auto / Ask / Off.
The worker owns the defaults (as it owns preflight's "would act" judgement),
hides Off tools from the model, and holds an Ask tool until a person in the
topic decides -- nucleus keeps the decision, the worker polls for it while
the run stays open, sending keepalives so the relay's stream never idles out.
"""
import asyncio
from types import SimpleNamespace

import pytest
from pydantic_ai.exceptions import SkipToolExecution

from apps.implementations.agents.stream_merge import merge_events
from apps.managers.approvals import (
    ApprovalOutcome, ApprovalRequest, NucleusApprovals, ToolApprovalGate, level_for, args_preview,
)
from apps.schemas.trigger import AgentEvent, AgentEventType


def tool_def(name, capability_id, metadata=None):
    return SimpleNamespace(name=name, capability_id=capability_id, metadata=metadata or {})


def call(name, call_id="c1"):
    return SimpleNamespace(tool_name=name, tool_call_id=call_id)


CTX = SimpleNamespace(tool_call_approved=False)


# ── levels ───────────────────────────────────────────────────────────────────
def test_defaults_read_is_automatic_and_acting_asks():
    assert level_for({}, "filesystem", "read_file") == "auto"
    assert level_for({}, "filesystem", "write_file") == "ask"
    assert level_for({}, "filesystem", "edit_file") == "ask"
    assert level_for({}, "filesystem", "create_directory") == "ask"
    assert level_for({}, "shell", "run_command") == "ask"
    assert level_for({}, "shell", "start_command") == "ask"
    assert level_for({}, "shell", "check_command") == "auto"
    assert level_for({}, "web_search", "duckduckgo_search") == "auto"
    assert level_for({}, "web_fetch", "web_fetch") == "auto"


def test_an_mcp_tool_asks_unless_its_annotations_say_read_only():
    assert level_for({}, "mcp:s1", "create_issue") == "ask"
    assert level_for({}, "mcp:s1", "list_issues", {"annotations": {"readOnlyHint": True}}) == "auto"
    assert level_for({}, "mcp:s1", "wipe", {"annotations": {"readOnlyHint": False}}) == "ask"


def test_a_capability_level_overrides_the_default_and_a_tool_level_overrides_that():
    levels = {"filesystem": "ask", "filesystem/read_file": "auto", "shell": "off", "shell/check_command": "auto", "mcp:s1": "auto"}
    assert level_for(levels, "filesystem", "list_directory") == "ask"
    assert level_for(levels, "filesystem", "read_file") == "auto"
    assert level_for(levels, "shell", "run_command") == "off"
    assert level_for(levels, "shell", "check_command") == "auto"
    assert level_for(levels, "mcp:s1", "create_issue") == "auto"


def test_a_level_nobody_recognises_falls_back_to_the_default():
    assert level_for({"shell": "sometimes"}, "shell", "run_command") == "ask"
    assert level_for({"shell": "sometimes"}, "shell", "check_command") == "auto"


def test_args_preview_is_one_short_line():
    assert args_preview({"command": "git status"}) == 'command: "git status"'
    assert args_preview({"path": "a.txt", "content": "x" * 400}).endswith("…")
    assert len(args_preview({"path": "a.txt", "content": "x" * 400})) <= 300
    assert args_preview({}) == ""


# ── the gate ─────────────────────────────────────────────────────────────────
class Asker:
    """What nucleus would answer, and what it was asked."""

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.asked: list[ApprovalRequest] = []

    async def __call__(self, request: ApprovalRequest) -> ApprovalOutcome:
        self.asked.append(request)
        return self.outcomes.pop(0)


@pytest.mark.asyncio
async def test_off_tools_are_hidden_from_the_model():
    gate = ToolApprovalGate(levels={"shell": "off", "filesystem/write_file": "off"}, ask=Asker())
    defs = [tool_def("run_command", "shell"), tool_def("read_file", "filesystem"), tool_def("write_file", "filesystem")]
    kept = await gate.prepare_tools(CTX, defs)
    assert [t.name for t in kept] == ["read_file"]


@pytest.mark.asyncio
async def test_an_auto_tool_runs_without_asking():
    asker = Asker()
    gate = ToolApprovalGate(levels={}, ask=asker)
    args = {"path": "a.txt"}
    assert await gate.before_tool_execute(CTX, call=call("read_file"), tool_def=tool_def("read_file", "filesystem"), args=args) is args
    assert asker.asked == []


@pytest.mark.asyncio
async def test_an_ask_tool_waits_for_the_person_and_runs_when_allowed():
    asker = Asker(ApprovalOutcome("allow"))
    gate = ToolApprovalGate(levels={}, ask=asker)
    args = {"command": "git push"}
    out = await gate.before_tool_execute(CTX, call=call("run_command", "c9"), tool_def=tool_def("run_command", "shell"), args=args)
    assert out is args
    assert asker.asked == [ApprovalRequest(call_id="c9", tool="run_command", capability_id="shell", args_preview='command: "git push"')]


@pytest.mark.asyncio
async def test_a_denied_call_is_skipped_with_a_reason_the_model_sees():
    gate = ToolApprovalGate(levels={}, ask=Asker(ApprovalOutcome("deny")))
    with pytest.raises(SkipToolExecution) as skipped:
        await gate.before_tool_execute(CTX, call=call("run_command"), tool_def=tool_def("run_command", "shell"), args={})
    assert "declined" in skipped.value.result  # the message becomes the tool's result


@pytest.mark.asyncio
async def test_a_timeout_and_a_stop_skip_the_call_too():
    gate = ToolApprovalGate(levels={}, ask=Asker(ApprovalOutcome("timeout"), ApprovalOutcome("stopped")))
    with pytest.raises(SkipToolExecution) as timed_out:
        await gate.before_tool_execute(CTX, call=call("write_file"), tool_def=tool_def("write_file", "filesystem"), args={})
    assert "Nobody decided on write_file" in timed_out.value.result
    with pytest.raises(SkipToolExecution) as stopped:
        await gate.before_tool_execute(CTX, call=call("write_file"), tool_def=tool_def("write_file", "filesystem"), args={})
    assert "stopped" in stopped.value.result


@pytest.mark.asyncio
async def test_always_allow_clears_that_tool_for_the_rest_of_the_run():
    asker = Asker(ApprovalOutcome("allow", always=True))
    gate = ToolApprovalGate(levels={}, ask=asker)
    for _ in range(2):
        await gate.before_tool_execute(CTX, call=call("run_command"), tool_def=tool_def("run_command", "shell"), args={})
    assert len(asker.asked) == 1
    # another tool of the same capability still asks
    asker.outcomes.append(ApprovalOutcome("allow"))
    await gate.before_tool_execute(CTX, call=call("start_command"), tool_def=tool_def("start_command", "shell"), args={})
    assert len(asker.asked) == 2


@pytest.mark.asyncio
async def test_the_gate_remembers_how_long_each_call_waited():
    """The trail should time the tool, not the person: the runner takes the wait off."""
    async def slow(_):
        await asyncio.sleep(0.05)
        return ApprovalOutcome("allow")
    gate = ToolApprovalGate(levels={}, ask=slow)
    await gate.before_tool_execute(CTX, call=call("run_command", "c7"), tool_def=tool_def("run_command", "shell"), args={})
    assert gate.waits["c7"] >= 0.05
    await gate.before_tool_execute(CTX, call=call("read_file", "c8"), tool_def=tool_def("read_file", "filesystem"), args={})
    assert "c8" not in gate.waits  # nothing waited


@pytest.mark.asyncio
async def test_a_run_nobody_is_watching_refuses_ask_tools_at_once():
    asker = Asker()
    gate = ToolApprovalGate(levels={}, ask=asker, interactive=False)
    with pytest.raises(SkipToolExecution) as refused:
        await gate.before_tool_execute(CTX, call=call("run_command"), tool_def=tool_def("run_command", "shell"), args={})
    assert "nobody can give one" in refused.value.result
    assert asker.asked == []


@pytest.mark.asyncio
async def test_a_call_the_framework_already_cleared_is_not_asked_again():
    asker = Asker()
    gate = ToolApprovalGate(levels={}, ask=asker)
    approved = SimpleNamespace(tool_call_approved=True)
    await gate.before_tool_execute(approved, call=call("run_command"), tool_def=tool_def("run_command", "shell"), args={})
    assert asker.asked == []


# ── the poller ───────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_the_poller_announces_the_request_then_polls_until_decided():
    answers = [{"status": "pending"}, {"status": "pending"}, {"status": "allowed", "always": True}]
    polled = []
    emitted = []

    async def poll(call_id):
        polled.append(call_id)
        return answers.pop(0)

    approvals = NucleusApprovals(msg_id="m1", poll=poll, emit=emitted.append, poll_seconds=0, timeout_seconds=5)
    outcome = await approvals(ApprovalRequest(call_id="c1", tool="run_command", capability_id="shell", args_preview="command: ls"))
    assert outcome == ApprovalOutcome("allow", always=True)
    assert polled == ["c1", "c1", "c1"]
    assert emitted[0].type == AgentEventType.APPROVAL_REQUESTED and emitted[0].approval.call_id == "c1"
    assert emitted[0].approval.tool == "run_command" and emitted[0].approval.args_preview == "command: ls"


@pytest.mark.asyncio
async def test_the_poller_maps_denied_stopped_and_silence_to_outcomes():
    async def denied(_): return {"status": "denied"}
    async def stopped(_): return {"status": "stopped"}
    async def silent(_): return {"status": "pending"}
    req = ApprovalRequest(call_id="c1", tool="t", capability_id="shell", args_preview="")
    assert (await NucleusApprovals("m", poll=denied, emit=lambda e: None, poll_seconds=0, timeout_seconds=5)(req)).decision == "deny"
    assert (await NucleusApprovals("m", poll=stopped, emit=lambda e: None, poll_seconds=0, timeout_seconds=5)(req)).decision == "stopped"
    assert (await NucleusApprovals("m", poll=silent, emit=lambda e: None, poll_seconds=0.01, timeout_seconds=0.03)(req)).decision == "timeout"


@pytest.mark.asyncio
async def test_a_poll_that_errors_keeps_waiting_rather_than_deciding():
    answers = [RuntimeError("nucleus hiccup"), {"status": "allowed"}]

    async def poll(_):
        a = answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return a

    outcome = await NucleusApprovals("m", poll=poll, emit=lambda e: None, poll_seconds=0, timeout_seconds=5)(
        ApprovalRequest(call_id="c1", tool="t", capability_id="shell", args_preview=""))
    assert outcome.decision == "allow"


# ── the stream merge ─────────────────────────────────────────────────────────
async def agen(items, delay=0):
    for item in items:
        if delay:
            await asyncio.sleep(delay)
        yield item


@pytest.mark.asyncio
async def test_side_events_are_yielded_between_the_stream_s_own_events():
    side: asyncio.Queue = asyncio.Queue()
    ev = AgentEvent(type=AgentEventType.APPROVAL_REQUESTED, id="m")
    side.put_nowait(ev)
    out = [e async for e in merge_events(agen(["a", "b"]), side, keepalive_seconds=10)]
    assert ev in out and out[-1] == "b" and len(out) == 3


@pytest.mark.asyncio
async def test_a_keepalive_is_sent_while_the_stream_is_silent():
    side: asyncio.Queue = asyncio.Queue()
    out = [e async for e in merge_events(agen(["a"], delay=0.05), side, keepalive_seconds=0.01, msg_id="m")]
    keepalives = [e for e in out if isinstance(e, AgentEvent) and e.type == AgentEventType.KEEPALIVE]
    assert keepalives and out[-1] == "a" and all(k.id == "m" for k in keepalives)


@pytest.mark.asyncio
async def test_a_side_event_arriving_mid_wait_is_not_delayed_until_the_next_stream_event():
    side: asyncio.Queue = asyncio.Queue()
    ev = AgentEvent(type=AgentEventType.APPROVAL_REQUESTED, id="m")
    loop = asyncio.get_running_loop()
    loop.call_later(0.01, side.put_nowait, ev)
    seen_at = {}

    async def collect():
        async for e in merge_events(agen(["a"], delay=0.08), side, keepalive_seconds=10):
            seen_at[e if isinstance(e, str) else "side"] = loop.time()
    await collect()
    assert seen_at["side"] < seen_at["a"]


# ── the persona payload ──────────────────────────────────────────────────────
def test_persona_from_carries_the_levels_and_names_each_mcp_server():
    from apps.managers.nucleus_client import persona_from
    data = {
        "id": "pe1", "name": "Sara", "prompt": {"system_prompt": "hi"},
        "model": {"id": "mc1", "provider": "openai", "model_id": "gpt-4o-mini", "qualified_id": "openai:gpt-4o-mini", "api_key": "k", "max_tokens": 100},
        "capabilities": [], "tool_levels": {"shell": "off"},
        "mcp_servers": [{"id": "s1", "name": "GitHub", "url": "https://mcp.example", "secrets": {"client_secret": "t"}, "auth_type": "static_secrets"}],
    }
    persona = persona_from(data)
    assert persona.tool_levels == {"shell": "off"}
    assert persona.mcp_servers[0].id == "s1" and persona.mcp_servers[0].name == "GitHub"
    data.pop("tool_levels")  # an older nucleus sends none
    assert persona_from(data).tool_levels == {}


# ── the agent the runner builds ──────────────────────────────────────────────
@pytest.mark.asyncio
async def test_build_agent_names_the_built_in_capabilities_and_mounts_the_gate(monkeypatch, tmp_path):
    """Every tool definition names its source, and the gate sits among the capabilities."""
    from pydantic_ai.capabilities import AbstractCapability
    from pydantic_ai.models.test import TestModel
    from apps.implementations.agents.pydantic_ai_runner import PydanticAIRunner
    from apps.schemas.trigger import FileSystem, ModelConfig, PersonaCapabilities, PersonaConfig, Shell

    seen: list[tuple[str, str | None]] = []

    class Probe(AbstractCapability):
        async def prepare_tools(self, ctx, tool_defs):
            seen.extend((t.name, t.capability_id) for t in tool_defs)
            return tool_defs

    monkeypatch.setattr(PydanticAIRunner, "_resolve_model", classmethod(lambda cls, persona: TestModel()))
    persona = PersonaConfig(
        id="pe1", name="Sara", system_prompt="hi", model=ModelConfig(provider="openai", model_id="x"), mcp_servers=[],
        capabilities=PersonaCapabilities(filesystem=FileSystem(root_dir=str(tmp_path)), shell=Shell(cwd=str(tmp_path))),
    )
    agent = PydanticAIRunner.build_agent(persona, Probe())
    async with agent:
        try:
            await agent.run("hi")
        except Exception:
            pass  # TestModel has no built-in tool support; the tool defs were prepared before it answered
    assert ("write_file", "filesystem") in seen and ("run_command", "shell") in seen
