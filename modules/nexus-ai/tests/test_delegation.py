"""
Layer 6, item 46 — call_persona: one-shot delegation to another persona
(docs/NEXUS-AI-REVAMP.md Layer 6 decision 5; trial I 3/3 on pinned 2.55.0;
built 2026-10-14).

A delegation-enabled persona runs another persona on a sub-task through the
engine's own inner respond(); the callee's finished reply is the tool result;
the inner run is unattended, depth-limited, and billed under the CALLEE's ids
on "{msg_id}:cp{n}". Personas without the flag never see the tool.
"""
from __future__ import annotations

import asyncio
import json

import pytest

from conftest import openai_model
from fake_nucleus import make_persona

pytestmark = pytest.mark.asyncio


def _by_type(events, kind):
    return [e for e in events if e["type"] == kind]


def _call_step(persona_id: str = "p-worker") -> dict:
    return {"kind": "tool_call", "call_id": "call_d1", "name": "call_persona",
            "args": {"persona_id": persona_id, "task": "Count the sales rows",
                     "summary": "The CSV was read earlier.",
                     "expected_output": "a single number"}}


async def _wait_for_record(harness, message_id: str, timeout: float = 10.0) -> dict:
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        for record in harness.usage_records():
            if record.get("message_id") == message_id:
                return record
        await asyncio.sleep(0.05)
    raise AssertionError(f"no record for {message_id}: {harness.usage_records()}")


async def test_d1_delegation_runs_the_callee_and_bills_it(harness):
    """Item 46 — the callee runs as itself; its reply is the tool result.
    A delegation-enabled supervisor calls call_persona('p-worker', …): the
    INNER request carries the worker's own system prompt and the rendered
    Handover; the worker's reply travels back as the tool result; the outer
    reply finishes; the inner call is billed under persona_id='p-worker' on
    message 'msg-1:cp0' while the outer run bills on 'msg-1'."""
    harness.nucleus.persona = make_persona(openai_model(harness), delegation_enabled=True)
    harness.nucleus.personas["p-worker"] = make_persona(
        openai_model(harness), persona_id="p-worker",
        system_prompt="You are the worker. WORKER-PROMPT-MARKER.")
    harness.provider.script.steps = [
        _call_step(),                                              # outer turn 1
        {"kind": "text", "text": "WORKER-REPLY: 42 rows found."},  # the INNER run
        {"kind": "text", "text": "The worker counted 42 rows."},   # outer turn 2
    ]
    events = await harness.trigger()
    [done] = _by_type(events, "message_done")
    assert done["content"].strip() == "The worker counted 42 rows."
    assert "call_persona" in (done.get("used_tools") or [])

    inner_request = harness.provider.requests[1]
    inner_sent = json.dumps(inner_request)
    assert "WORKER-PROMPT-MARKER" in inner_sent      # the CALLEE's persona ran
    assert "Task: Count the sales rows" in inner_sent  # the Handover, rendered
    assert "The CSV was read earlier." in inner_sent
    outer_final = json.dumps(harness.provider.requests[2])
    assert "WORKER-REPLY: 42 rows found." in outer_final  # reply = tool result

    inner_record = await _wait_for_record(harness, "msg-1:cp0")
    assert inner_record["persona_id"] == "p-worker"
    outer_record = await _wait_for_record(harness, "msg-1")
    assert outer_record["persona_id"] == "p1"


async def test_d2_depth_limit_and_unattended_inner_run(harness):
    """Item 46 — depth 1: the callee can neither delegate nor ask.
    The callee ALSO has delegation enabled, yet the inner request carries no
    tools at all — no call_persona (delegation_depth=1) and no ask_user (the
    inner run is interactive=false; nobody could answer) — while the outer
    request does carry call_persona."""
    harness.nucleus.persona = make_persona(openai_model(harness), delegation_enabled=True)
    harness.nucleus.personas["p-worker"] = make_persona(
        openai_model(harness), persona_id="p-worker", delegation_enabled=True)
    harness.provider.script.steps = [
        _call_step(),
        {"kind": "text", "text": "Inner answer."},
        {"kind": "text", "text": "Done."},
    ]
    events = await harness.trigger()
    assert _by_type(events, "message_done")
    outer_names = [t["function"]["name"] for t in harness.provider.requests[0].get("tools", [])]
    assert "call_persona" in outer_names
    inner_tools = harness.provider.requests[1].get("tools") or []
    assert inner_tools == [], f"the callee got tools it must not have: {inner_tools}"


async def test_d3_personas_without_the_flag_never_see_the_tool(harness):
    """Item 46 — delegation is opt-in: no flag, no tool.
    The default persona (delegation_enabled absent → false) answers a plain
    message: the request carries only item 5's ask_user — call_persona appears
    nowhere."""
    harness.provider.script.text = "Plain answer."
    events = await harness.trigger()
    assert _by_type(events, "message_done")
    body = harness.provider.requests[-1]
    names = [t["function"]["name"] for t in body.get("tools", [])]
    assert names == ["ask_user"]
    assert "call_persona" not in json.dumps(body)
