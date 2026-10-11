"""
W4 Routines: a job may name a routine; the worker fetches it (like the
persona) and applies it for that turn only -- its instructions as their own
block after the persona prompt, its capability list narrowing the persona's
tools (never widening), its model replacing the persona's.
"""
import pytest

from apps.managers.routines import ROUTINE_HEADING, RoutineConfig, apply_routine, routine_from
from apps.schemas.trigger import (
    FileSystem, MCPArgs, ModelConfig, PersonaCapabilities, PersonaConfig, Shell, Thinking, TriggerJob, WebSearchArgs,
)


def persona(**over) -> PersonaConfig:
    base = dict(
        id="pe1", name="Sara", system_prompt="You are Sara.",
        model=ModelConfig(provider="openai", model_id="gpt-4o-mini", api_key="k1"),
        mcp_servers=[MCPArgs(id="s1", name="Jira", url="https://a"), MCPArgs(id="s2", name="GitHub", url="https://b")],
        capabilities=PersonaCapabilities(shell=Shell(cwd="/p"), filesystem=FileSystem(root_dir="/p"), web_search=WebSearchArgs(), thinking=Thinking()),
    )
    base.update(over)
    return PersonaConfig(**base)


def routine(**over) -> RoutineConfig:
    base = dict(id="r1", name="weekly-digest", title="Weekly digest", instructions="Write the digest.", allowed_capabilities=None, model=None)
    base.update(over)
    return RoutineConfig(**base)


def test_the_instructions_join_the_system_prompt_after_the_persona_s_own():
    out = apply_routine(persona(), routine())
    assert out.system_prompt == f"You are Sara.\n\n{ROUTINE_HEADING.format(title='Weekly digest')}\nWrite the digest."
    assert out.model == persona().model and out.mcp_servers == persona().mcp_servers  # nothing else moved


def test_allowed_capabilities_narrow_the_persona_s_tools_and_never_widen_them():
    out = apply_routine(persona(), routine(allowed_capabilities=["filesystem", "thinking", "mcp:s2", "web_fetch"]))
    caps = out.capabilities
    assert caps.filesystem is not None and caps.thinking is not None
    assert caps.shell is None and caps.web_search is None
    assert caps.web_fetch is None  # the persona never had it; the routine cannot add it
    assert [s.id for s in out.mcp_servers] == ["s2"]
    empty = apply_routine(persona(), routine(allowed_capabilities=[]))
    assert empty.mcp_servers == [] and empty.capabilities == PersonaCapabilities()


def test_a_routine_model_replaces_the_persona_s_for_the_turn():
    small = ModelConfig(provider="openai", model_id="gpt-4o-mini", api_key="k2")
    out = apply_routine(persona(), routine(model=small))
    assert out.model == small
    assert persona().model.api_key == "k1"  # the persona itself is untouched


def test_routine_from_reads_nucleus_s_payload_with_or_without_a_model():
    r = routine_from({"id": "r1", "name": "n", "title": "T", "instructions": "do", "allowed_capabilities": ["shell"],
                      "model": {"id": "m", "provider": "openai", "model_id": "gpt-4o-mini", "api_key": "k", "max_tokens": 50}})
    assert (r.allowed_capabilities, r.model.model_id, r.model.api_key) == (["shell"], "gpt-4o-mini", "k")
    assert routine_from({"id": "r1", "name": "n", "title": "T", "instructions": "do"}).model is None


def test_the_job_carries_an_optional_routine_id():
    assert TriggerJob(job_id="j", msg_id="m", persona_id="p", topic_id="t", user_message_id="u", message="x").routine_id is None
    assert TriggerJob(job_id="j", msg_id="m", persona_id="p", topic_id="t", user_message_id="u", message="x", routine_id="r1").routine_id == "r1"


@pytest.mark.asyncio
async def test_the_manager_applies_the_routine_before_the_prompt_is_built(monkeypatch):
    """The run fetches the routine the job names and the runner sees the narrowed, instructed persona."""
    from apps.managers import agentic_manager
    from apps.managers.agentic_manager import NewImprovedAgenticManager
    from apps.schemas.trigger import AgentEvent, AgentEventType

    seen = {}

    class Runner:
        async def run_stream(self, job, messages, persona, tools=None):
            seen["persona"] = persona
            yield AgentEvent(type=AgentEventType.DELTA, id=job.msg_id, delta="ok")

    async def fake_persona(_): return persona()
    async def fake_history(**_): return []
    async def fake_routine(rid):
        assert rid == "r1"
        return routine(allowed_capabilities=["shell"])
    async def fake_resolve(_, __=()): return "text", None
    monkeypatch.setattr(agentic_manager.nucleus_client, "resolve_persona", fake_persona)
    monkeypatch.setattr(agentic_manager.nucleus_client, "fetch_history", fake_history)
    monkeypatch.setattr(agentic_manager.nucleus_client, "resolve_routine", fake_routine)
    monkeypatch.setattr(agentic_manager, "resolve_output_spec", fake_resolve)
    manager = NewImprovedAgenticManager(runner=Runner(), embedder=None, store=None)
    job = TriggerJob(job_id="j", msg_id="m", persona_id="p", topic_id="t", user_message_id="u", message="x", routine_id="r1")
    [e async for e in manager.run(job)]
    assert "Weekly digest" in seen["persona"].system_prompt
    assert seen["persona"].capabilities.filesystem is None and seen["persona"].capabilities.shell is not None
    assert seen["persona"].mcp_servers == []
