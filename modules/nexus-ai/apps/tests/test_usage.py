"""
Usage accounting on the worker side: every run reports what it consumed on
its events (nucleus writes the rows), and the optional debug file gets the
full prompt and response -- never the database.
"""
import json
from contextlib import asynccontextmanager
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from pydantic_ai.usage import RunUsage

from apps.schemas.trigger import (
    AgentEvent, AgentEventType, ModelConfig, PersonaCapabilities, PersonaConfig, TriggerJob, UsageData,
)


def persona_config() -> PersonaConfig:
    return PersonaConfig(
        id="pe1", name="Sara", system_prompt="be brief",
        model=ModelConfig(id="mc1", provider="anthropic", model_id="claude-x"),
        mcp_servers=[], capabilities=PersonaCapabilities(),
    )


def job() -> TriggerJob:
    return TriggerJob(job_id="job1", msg_id="msg1", persona_id="pe1", topic_id="t1", user_message_id="u1", message="hi", actor_user_id="user1")


class TestUsageData:
    def test_maps_every_counter_and_the_cost(self):
        u = RunUsage(input_tokens=10, output_tokens=5, cache_read_tokens=2, cache_write_tokens=1, requests=2, tool_calls=3, cost=Decimal("0.0123"))
        assert UsageData.from_run_usage(u).model_dump() == {
            "input_tokens": 10, "output_tokens": 5, "cache_read_tokens": 2, "cache_write_tokens": 1,
            "requests": 2, "tool_calls": 3, "cost_usd": 0.0123,
        }

    def test_cost_stays_none_when_the_library_has_no_price(self):
        assert UsageData.from_run_usage(RunUsage(input_tokens=1)).cost_usd is None


class StubHandle:
    """What agent.run_stream_events() hands out: an async iterator with usage() and new_messages()."""
    def __init__(self, usage: RunUsage):
        self._usage = usage
    def __aiter__(self):
        return self
    async def __anext__(self):
        raise StopAsyncIteration
    def usage(self):
        return self._usage
    def new_messages(self):
        return []


class StubAgent:
    def __init__(self, usage: RunUsage):
        self._usage = usage
    @asynccontextmanager
    async def run_stream_events(self, **_kw):
        yield StubHandle(self._usage)


@pytest.mark.asyncio
async def test_runner_reports_the_run_usage_on_its_persist_event(monkeypatch):
    from apps.implementations.agents.pydantic_ai_runner import PydanticAIRunner
    monkeypatch.setattr(PydanticAIRunner, "build_agent", staticmethod(lambda persona: StubAgent(RunUsage(input_tokens=10, output_tokens=5, requests=1))))
    events = [e async for e in PydanticAIRunner().run_stream(job(), [], persona_config())]
    persist = next(e for e in events if e.type == AgentEventType.PERSIST)
    assert persist.usage is not None
    assert (persist.usage.input_tokens, persist.usage.output_tokens, persist.usage.requests) == (10, 5, 1)


class FakeRunner:
    """Yields a delta, then the persist event carrying usage -- what the real runner does."""
    def __init__(self, usage: UsageData):
        self.usage = usage
    async def run_stream(self, job, messages, persona, tools=None):
        yield AgentEvent(type=AgentEventType.DELTA, id=job.msg_id, delta="Hello")
        yield AgentEvent(type=AgentEventType.PERSIST, id=job.msg_id, metadata={"internal_model_state": []}, usage=self.usage)


@pytest.mark.asyncio
async def test_manager_stamps_usage_on_message_done_and_writes_the_debug_file(monkeypatch, tmp_path):
    from apps.managers import agentic_manager, nucleus_client
    from apps.core.config import settings
    monkeypatch.setattr(nucleus_client, "resolve_persona", AsyncMock(return_value=persona_config()))
    monkeypatch.setattr(nucleus_client, "fetch_history", AsyncMock(return_value=[]))
    debug_file = tmp_path / "ai-requests.jsonl"
    monkeypatch.setattr(settings, "AI_REQUEST_DEBUG_LOG", str(debug_file))

    usage = UsageData(input_tokens=7, output_tokens=3, requests=1, cost_usd=0.002)
    manager = agentic_manager.NewImprovedAgenticManager(runner=FakeRunner(usage), embedder=None, store=None)
    manager.prompt_builder.build = AsyncMock(return_value=[])
    events = [e async for e in manager.run(job())]

    done = next(e for e in events if e.type == AgentEventType.END)
    assert done.usage == usage
    assert done.content == "Hello"
    # The persist event is the runner's business; it never leaves the manager.
    assert all(e.type != AgentEventType.PERSIST for e in events)

    lines = debug_file.read_text().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["job_id"] == "job1" and record["msg_id"] == "msg1" and record["actor_user_id"] == "user1"
    assert record["persona"] == {"id": "pe1", "name": "Sara"}
    assert record["model"] == {"id": "mc1", "provider": "anthropic", "model_id": "claude-x"}
    assert record["response"] == "Hello" and record["usage"]["input_tokens"] == 7
    assert "prompt" in record


@pytest.mark.asyncio
async def test_no_debug_file_is_written_when_the_setting_is_unset(monkeypatch, tmp_path):
    from apps.managers import agentic_manager, nucleus_client
    from apps.core.config import settings
    monkeypatch.setattr(nucleus_client, "resolve_persona", AsyncMock(return_value=persona_config()))
    monkeypatch.setattr(nucleus_client, "fetch_history", AsyncMock(return_value=[]))
    monkeypatch.setattr(settings, "AI_REQUEST_DEBUG_LOG", "")
    manager = agentic_manager.NewImprovedAgenticManager(runner=FakeRunner(UsageData()), embedder=None, store=None)
    manager.prompt_builder.build = AsyncMock(return_value=[])
    [e async for e in manager.run(job())]
    assert list(tmp_path.iterdir()) == []


def test_resolve_persona_keeps_the_model_config_id(monkeypatch):
    from apps.managers import nucleus_client
    payload = {
        "id": "pe1", "name": "Sara", "prompt": {"system_prompt": "x"},
        "model": {"id": "mc1", "provider": "anthropic", "model_id": "claude-x", "api_key": "k", "max_tokens": 100, "temperature": 0.5},
        "mcp_servers": [], "capabilities": [],
    }
    class Resp:
        def raise_for_status(self): pass
        def json(self): return payload
    class Client:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, *a, **k): return Resp()
    monkeypatch.setattr(nucleus_client.httpx, "AsyncClient", Client)
    import asyncio
    persona = asyncio.run(nucleus_client.resolve_persona("pe1"))
    assert persona.model.id == "mc1"
