"""
Layer 4, item 5 — the model asks the user questions
(docs/NEXUS-AI-REVAMP.md Layer 4 decision 1 + trial H; built 2026-10-13).

ask_user is a REAL pausing tool on item 2's road: calling it ends the run with
a question_asked event and message_paused; the person's ANSWER rides the
resume (ResumeBlock.answers) as the tool result. Unattended runs never get the
tool — nobody can answer.
"""
from __future__ import annotations

import json

import pytest

pytestmark = pytest.mark.asyncio

ASK_STEP = {"kind": "tool_call", "call_id": "call_q1", "name": "ask_user",
            "args": {"question": "Which environment?", "options": ["dev", "prod"]}}


def _by_type(events, kind):
    return [e for e in events if e["type"] == kind]


async def test_q1_ask_user_pauses_with_the_question(harness):
    """Item 5 — asking pauses the run; the question rides its own event.
    The model calls ask_user → question_asked carries call_id, the question and
    the options; the stream ends with message_paused (no done, no error); the
    pause state lands on nucleus FIRST with pending kind='question'; the asking
    call's usage is still recorded."""
    harness.provider.script.steps = [ASK_STEP]
    events = await harness.trigger()

    types = [e["type"] for e in events]
    assert types[-1] == "message_paused"
    assert "message_done" not in types and "message_error" not in types
    [q] = _by_type(events, "question_asked")
    assert q["question"]["call_id"] == "call_q1"
    assert q["question"]["question"] == "Which environment?"
    assert q["question"]["options"] == ["dev", "prod"]

    [pause] = harness.nucleus.pause_posts
    assert pause["pending"][0]["tool"] == "ask_user"
    assert pause["pending"][0]["kind"] == "question"
    assert "Which environment?" in pause["pending"][0]["args_preview"]
    records = await harness.wait_for_usage(1)
    assert records[0]["message_id"] == "msg-1"


async def test_q2_answer_resumes_and_reaches_the_model(harness):
    """Item 5 — the person's answer IS the tool result; the reply finishes.
    Pause first; then the resume carries answers={call_q1: 'prod, please'} —
    the model receives exactly that text as ask_user's result (visible in the
    provider request) and completes with message_done; both halves billed."""
    harness.provider.script.steps = [ASK_STEP, {"kind": "text", "text": "Deploying to prod."}]
    events = await harness.trigger()
    assert events[-1]["type"] == "message_paused"
    [pause] = harness.nucleus.pause_posts

    resume_job = harness.job(resume={
        "state": pause["state"],
        "answers": {"call_q1": "prod, please"},
        "role": pause["role"],
    })
    events = await harness.trigger(resume_job)
    [done] = _by_type(events, "message_done")
    assert done["content"].strip() == "Deploying to prod."
    sent = json.dumps(harness.provider.requests[-1])
    assert "prod, please" in sent  # the answer travelled as the tool result
    records = await harness.wait_for_usage(2)
    assert len(records) == 2


async def test_q3_unattended_run_has_no_ask_user(harness):
    """Item 5 — interactive=false: the tool simply doesn't exist.
    Nobody can answer in a scheduled run, so ask_user is never offered — the
    provider request carries no ask_user schema and the model answers normally
    with message_done."""
    harness.provider.script.text = "Answered without asking."
    events = await harness.trigger(harness.job(interactive=False))
    [done] = _by_type(events, "message_done")
    assert done["content"].strip() == "Answered without asking."
    assert "ask_user" not in json.dumps(harness.provider.requests[-1])
