"""
Layer 4 — nudges (W8) and the memory pass (item 27, decision 8)
(docs/NEXUS-AI-REVAMP.md Layer 4 decisions 3 + 8; built 2026-10-13).

Nudges: what the caller types while the reply runs reaches the model with the
NEXT tool result, announced by nudge_taken; a toolless run takes nothing.
Memory pass: after a tool-bearing reply, one cheap call on the UTILITY →
ROUTER → STANDARD chain rules raw/summary/skip per output; saved rows carry
tool+command+timestamp; billed kind="memory"; failure never touches the reply.
"""
from __future__ import annotations

import asyncio
import json

import pytest

from conftest import INTERNAL_KEY, openai_model
from fake_nucleus import make_persona

pytestmark = pytest.mark.asyncio


def _by_type(events, kind):
    return [e for e in events if e["type"] == kind]


def _fs_persona(harness, tmp_path, **kw) -> dict:
    return make_persona(
        openai_model(harness),
        capabilities=[{"id": "cap1", "name": "defaults",
                       "capability_config": {"filesystem": {"root_dir": str(tmp_path)}}}],
        **kw,
    )


def _read_step(path: str) -> dict:
    return {"kind": "tool_call", "call_id": "call_r1", "name": "read_file",
            "args": {"path": path}}


async def test_n1_nudge_reaches_the_model_and_the_stream(harness, tmp_path):
    """W8 — a waiting nudge rides the next tool result, announced on the wire.
    A nudge is queued before the reply; the model's read_file runs; the NEXT
    provider request shows the tool result carrying '[The reader adds while you
    work: …]', the stream carries nudge_taken with the text, and nucleus's
    store was consumed (taken once)."""
    (tmp_path / "notes.txt").write_text("plain content")
    harness.nucleus.persona = _fs_persona(harness, tmp_path)
    harness.nucleus.nudges = {"msg-1": ["also check prod"]}
    harness.provider.script.steps = [_read_step("notes.txt"),
                                     {"kind": "text", "text": "Done reading."}]
    events = await harness.trigger()

    [taken] = _by_type(events, "nudge_taken")
    assert taken["nudge"] == "also check prod"
    assert _by_type(events, "message_done")
    sent = json.dumps(harness.provider.requests[-1])
    assert "The reader adds while you work: also check prod" in sent
    assert harness.nucleus.nudges == {}  # consumed exactly once


async def test_n2_toolless_run_never_takes_a_nudge(harness):
    """W8 — no tool step, no nudge: nucleus keeps it to post after the reply.
    A plain text reply with a nudge waiting: no nudge_taken event, and the
    nudge is still in nucleus's store (nexus-ai never polled) — 0.8.0's
    never-lost rule, kept."""
    harness.nucleus.nudges = {"msg-1": ["too late for this run"]}
    harness.provider.script.text = "Plain answer."
    events = await harness.trigger()
    assert not _by_type(events, "nudge_taken")
    assert _by_type(events, "message_done")
    assert harness.nucleus.nudges == {"msg-1": ["too late for this run"]}


def _seed_index(company: str, project: str) -> None:
    """The project's index exists before the pass runs (decision 8: nucleus's
    embed calls create it with the project's own embedder — hash in tests)."""
    from fastapi_app.routers.embed import get_store
    from ai_engine.core.specs import VectorItem
    get_store().index(company, project, [VectorItem(
        id="seed", kind="recall", text="seed row", label="seed", source="seed")],
        embedder_spec={"provider": "hash", "model_id": "hash-768"})


def _rulings_step(rulings: list[dict], call_id: str = "call_mem") -> dict:
    return {"kind": "tool_call", "call_id": call_id, "name": "final_result",
            "args": {"rulings": rulings}}


async def _wait_memory_record(harness, timeout: float = 10.0) -> dict:
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        for record in harness.usage_records():
            if record.get("kind") == "memory":
                return record
        await asyncio.sleep(0.05)
    raise AssertionError(f"no kind=memory record: {harness.usage_records()}")


async def test_m1_memory_pass_saves_a_summary_with_provenance(harness, tmp_path, vector_url):
    """Decision 8 — the pass saves what the model ruled, with provenance, billed.
    A read_file output is ruled 'summary' by the scripted utility seat: one
    kind='tool_result' row lands in the project index carrying the summary
    text, tool+args in the label, the topic id and a timestamp — and a
    kind='memory' usage record bills the pass under the UTILITY seat's model."""
    (tmp_path / "sales.csv").write_text("march,48200\napril,51000")
    harness.nucleus.persona = _fs_persona(
        harness, tmp_path,
        utility_model=openai_model(harness, config_id="m-util", model_id="util-model"))
    harness.provider.script.steps = [
        _read_step("sales.csv"),
        {"kind": "text", "text": "March sales were 48200."},
        _rulings_step([{"index": 0, "action": "summary",
                        "summary": "sales.csv: march 48200, april 51000 (read from project file)"}]),
    ]
    _seed_index("c-mem", "pr-mem")  # decision 8: the pass joins an EXISTING index
    job = harness.job(company_id="c-mem", project_id="pr-mem", topic_id="t-mem")
    events = await harness.trigger(job)
    assert _by_type(events, "message_done")

    record = await _wait_memory_record(harness)
    assert record["model_id"] == "util-model" and record["kind"] == "memory"

    from fastapi_app.routers.embed import get_store
    from ai_engine.core.specs import SearchQuery
    store = get_store()
    for _ in range(50):
        hits = store.search(SearchQuery(company_id="c-mem", project_id="pr-mem",
                                        text="march sales", kinds=("tool_result",),
                                        topic_id="t-mem", min_score=0.01))
        if hits:
            break
        await asyncio.sleep(0.1)
    assert hits and hits[0].id == "msg-1:tr0"
    assert "48200" in hits[0].text
    assert "read_file" in hits[0].label and "sales.csv" in hits[0].label
    assert hits[0].created_at  # the staleness timestamp travels


async def test_m2_skip_ruling_saves_nothing_but_still_bills(harness, tmp_path, vector_url):
    """Decision 8 — 'skip' is a decision too: nothing saved, the pass billed.
    The scripted seat rules skip for a local file read: no tool_result rows
    appear for this message, and the reply itself was never touched (done came
    first, pass after)."""
    (tmp_path / "local.txt").write_text("re-runnable local content")
    harness.nucleus.persona = _fs_persona(
        harness, tmp_path,
        utility_model=openai_model(harness, config_id="m-util", model_id="util-model"))
    harness.provider.script.steps = [
        _read_step("local.txt"),
        {"kind": "text", "text": "Read it."},
        _rulings_step([{"index": 0, "action": "skip"}]),
    ]
    _seed_index("c-mem", "pr-mem2")
    job = harness.job(msg_id="msg-skip", company_id="c-mem", project_id="pr-mem2", topic_id="t-mem")
    events = await harness.trigger(job)
    assert _by_type(events, "message_done")
    await _wait_memory_record(harness)

    from fastapi_app.routers.embed import get_store
    from ai_engine.core.specs import SearchQuery
    hits = get_store().search(SearchQuery(company_id="c-mem", project_id="pr-mem2",
                                          text="local content", min_score=0.0))
    assert all(not h.id.startswith("msg-skip:") for h in hits)
