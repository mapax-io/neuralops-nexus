"""
Layer 1, item 2 decision 4 — ToolSearch ask-on-first-use
(docs/NEXUS-AI-REVAMP.md §1.3; trial F, 2026-10-13) — and item 19's activity
trail (tool_call_start / tool_call_end, 0.8.0 shapes).

Through the running service: tools outside the topic's loaded set are hidden
until the model discovers them with search_tools; the discovered tool's FIRST
use pauses for the person; loaded tools emit start/end activity events.
"""
from __future__ import annotations

import pytest

from fake_nucleus import make_persona
from conftest import openai_model

pytestmark = pytest.mark.asyncio


def _fs_persona(harness, tmp_path) -> dict:
    return make_persona(
        openai_model(harness),
        capabilities=[{"id": "cap1", "name": "defaults",
                       "capability_config": {"filesystem": {"root_dir": str(tmp_path)}}}],
    )


def _search_step() -> dict:
    return {"kind": "tool_call", "call_id": "call_s1", "name": "search_tools",
            "args": {"queries": ["read a file"]}}


def _read_step(path: str = "data.txt") -> dict:
    return {"kind": "tool_call", "call_id": "call_d1", "name": "read_file",
            "args": {"path": path}}


async def test_f1_unloaded_tools_hidden_until_discovered(harness, tmp_path):
    """Decision 4 — tools outside the topic's set are INVISIBLE until discovered.
    topic_tools=[] hides every filesystem tool: request 1 carries only the
    search_tools schema (plus item 5's built-in ask_user); after the model searches, the discovered tool's schema
    appears in the next request — and its FIRST use pauses the run for the
    person (ask on first use), even though read_file is a read."""
    (tmp_path / "data.txt").write_text("DISCOVERED-61")
    harness.nucleus.persona = _fs_persona(harness, tmp_path)
    harness.provider.script.steps = [_search_step(), _read_step()]
    events = await harness.trigger(harness.job(topic_tools=[]))

    types = [e["type"] for e in events]
    assert types[-1] == "message_paused"
    [req] = [e for e in events if e["type"] == "approval_requested"]
    assert req["approval"]["tool"] == "read_file"

    first = harness.provider.requests[0]
    names1 = [t["function"]["name"] for t in first.get("tools", [])]
    # item 5's ask_user always rides; everything else must stay hidden
    assert sorted(names1) == ["ask_user", "search_tools"], f"hidden tools leaked: {names1}"
    second = harness.provider.requests[1]
    names2 = [t["function"]["name"] for t in second.get("tools", [])]
    assert "read_file" in names2  # discovery surfaced the schema


async def test_f2_approved_first_use_executes_and_finishes(harness, tmp_path):
    """Decision 4 — approving the first use runs the tool; the set updates nucleus-side.
    The resume executes read_file (the file's real content reaches the model as
    the tool result) and the reply finishes; adding the tool to topic_tools is
    nucleus's half of change 8 — our half is the approval card it acts on."""
    (tmp_path / "data.txt").write_text("DISCOVERED-61")
    harness.nucleus.persona = _fs_persona(harness, tmp_path)
    harness.provider.script.steps = [
        _search_step(), _read_step(), {"kind": "text", "text": "It says DISCOVERED-61."},
    ]
    await harness.trigger(harness.job(topic_tools=[]))
    [pause] = harness.nucleus.pause_posts
    call_id = pause["pending"][0]["call_id"]

    job = harness.job(topic_tools=[],
                      resume={"state": pause["state"],
                              "approvals": {call_id: {"decision": "allow"}}})
    events = await harness.trigger(job)
    assert [e for e in events if e["type"] == "message_done"]
    body = harness.provider.requests[-1]
    tool_msgs = [m for m in body["messages"] if m.get("role") == "tool"]
    assert any("DISCOVERED-61" in m["content"] for m in tool_msgs)


async def test_f3_unattended_discovery_is_refused_not_paused(harness, tmp_path):
    """Decision 4 — in an unattended run a discovered tool is refused, never paused.
    Nobody can approve the first use in a schedule: the model hears the
    "needs a person's approval" text as the tool result and the reply still
    ends in message_done with no pause stored."""
    (tmp_path / "data.txt").write_text("X")
    harness.nucleus.persona = _fs_persona(harness, tmp_path)
    harness.provider.script.steps = [
        _search_step(), _read_step(), {"kind": "text", "text": "Could not read it."},
    ]
    events = await harness.trigger(harness.job(topic_tools=[], interactive=False))
    types = [e["type"] for e in events]
    assert "message_paused" not in types and types[-1] == "message_done"
    assert not harness.nucleus.pause_posts
    body = harness.provider.requests[-1]
    tool_msgs = [m for m in body["messages"] if m.get("role") == "tool"]
    assert any("needs a person's approval" in m["content"] for m in tool_msgs)


# ── item 19: the activity trail ─────────────────────────────────────────────────

async def test_i19_tool_activity_events(harness, tmp_path):
    """Item 19 — a loaded tool's run emits tool_call_start and tool_call_end.
    read_file (auto, loaded) → the stream carries tool_call_start (name + args)
    before tool_call_end (ok=true, duration_ms, clipped preview of the real
    content) — 0.8.0's event names and ToolCallData/ToolResultData shapes, so
    nucleus's activity trail keeps working unchanged."""
    (tmp_path / "data.txt").write_text("ACTIVITY-19")
    harness.nucleus.persona = _fs_persona(harness, tmp_path)
    harness.provider.script.steps = [
        _read_step(), {"kind": "text", "text": "Read it."},
    ]
    events = await harness.trigger()
    types = [e["type"] for e in events]
    assert "tool_call_start" in types and "tool_call_end" in types
    assert types.index("tool_call_start") < types.index("tool_call_end")

    [start] = [e for e in events if e["type"] == "tool_call_start"]
    assert start["tool_call"]["name"] == "read_file"
    assert start["tool_call"]["args"]["path"] == "data.txt"
    [end] = [e for e in events if e["type"] == "tool_call_end"]
    assert end["tool_result"]["name"] == "read_file"
    assert end["tool_result"]["ok"] is True
    assert "ACTIVITY-19" in end["tool_result"]["preview"]
    assert end["tool_result"]["duration_ms"] >= 0
    assert [e for e in events if e["type"] == "message_done"]
