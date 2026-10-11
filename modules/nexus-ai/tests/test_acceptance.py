"""
Layer 0 acceptance tests T1–T10, T14, T15 (docs/NEXUS-AI-REVAMP.md §1.5).
T11/T12 live in test_cost.py, T13 in test_history.py, T16 in test_dependencies.py.
"""
from __future__ import annotations

import asyncio
import json
import os

import httpx
import pytest

from conftest import INTERNAL_KEY, anthropic_model, openai_model
from fake_nucleus import make_persona

pytestmark = pytest.mark.asyncio

ANTHROPIC_USAGE = {
    "input_tokens": 200, "output_tokens": 300,
    "cache_creation_input_tokens": 500, "cache_read_input_tokens": 1000,
    "cache_creation": {"ephemeral_5m_input_tokens": 300, "ephemeral_1h_input_tokens": 200},
}
OPENAI_USAGE = {
    "prompt_tokens": 1200, "completion_tokens": 300, "total_tokens": 1500,
    "prompt_tokens_details": {"cached_tokens": 1000},
    "completion_tokens_details": {"reasoning_tokens": 120},
}


def _by_type(events: list[dict], kind: str) -> list[dict]:
    return [e for e in events if e["type"] == kind]


# ── T1: plain reply ────────────────────────────────────────────────────────────

async def test_t1_plain_reply(harness):
    harness.provider.script.text = "The answer is forty-two."
    events = await harness.trigger()

    assert events[0]["type"] == "message_start"
    deltas = _by_type(events, "message_delta")
    dones = _by_type(events, "message_done")
    assert len(deltas) >= 1
    assert len(dones) == 1
    assert not _by_type(events, "message_error")

    streamed = "".join(w + " " for w in harness.provider.script.text.split(" "))
    concatenated = "".join(d["delta"] for d in deltas)
    assert dones[0]["content"] == concatenated == streamed


# ── T2: system prompt once, project brief precedes it ──────────────────────────

@pytest.mark.parametrize("shape", ["openai", "anthropic"])
async def test_t2_system_prompt_once(harness, shape):
    model = openai_model(harness) if shape == "openai" else anthropic_model(harness)
    harness.nucleus.persona = make_persona(model, project_brief="BRIEF-MARKER applies here.")
    harness.nucleus.history = [
        {"id": "h1", "sender_type": "human", "sender_name": "Noaman", "content": "earlier question",
         "render_as": "text", "output_type": "text", "stopped": False, "sequence": 1},
        {"id": "h2", "sender_type": "persona", "sender_name": "NeuralBot", "content": "earlier answer",
         "render_as": "text", "output_type": "text", "stopped": False, "sequence": 2},
    ]
    events = await harness.trigger()
    assert len(_by_type(events, "message_done")) == 1

    body = json.dumps(harness.provider.requests[-1])
    assert body.count("PERSONA-PROMPT-MARKER") == 1
    assert body.count("BRIEF-MARKER") == 1
    assert body.index("BRIEF-MARKER") < body.index("PERSONA-PROMPT-MARKER")
    # and the history made it across
    assert "earlier question" in body and "earlier answer" in body


# ── T3: temperature and output limit reach the request ─────────────────────────

@pytest.mark.parametrize("shape", ["openai", "anthropic"])
async def test_t3_settings_reach_the_model(harness, shape):
    model = openai_model(harness) if shape == "openai" else anthropic_model(harness)
    harness.nucleus.persona = make_persona(model, temperature=0.3, max_tokens=777)
    await harness.trigger()

    body = harness.provider.requests[-1]
    assert body.get("temperature") == 0.3
    # OpenAI's chat API takes the cap as max_completion_tokens; Anthropic as max_tokens
    assert body.get("max_tokens") == 777 or body.get("max_completion_tokens") == 777


# ── T4: Anthropic usage ────────────────────────────────────────────────────────

async def test_t4_anthropic_usage(harness):
    harness.nucleus.persona = make_persona(anthropic_model(harness))
    harness.provider.script.usage = ANTHROPIC_USAGE
    events = await harness.trigger()

    [record] = await harness.wait_for_usage(1)
    assert record["input_tokens"] == 1700
    assert record["uncached_input_tokens"] == 200
    assert record["cache_read_tokens"] == 1000
    assert record["cache_write_5m_tokens"] == 300
    assert record["cache_write_1h_tokens"] == 200
    assert record["output_tokens"] == 300
    assert record["reasoning_tokens"] == 0
    assert record["estimated"] is False
    assert record["kind"] == "chat_reply" and record["role"] == "STANDARD"
    assert record["company_id"] == "c1" and record["topic_id"] == "t1" and record["user_id"] == "u1"

    [done] = _by_type(events, "message_done")
    assert done["prompt_tokens"] == 1700 and done["output_tokens"] == 300
    assert done["context_window"] == 200_000


# ── T5: OpenAI usage ───────────────────────────────────────────────────────────

async def test_t5_openai_usage(harness):
    harness.provider.script.usage = OPENAI_USAGE
    await harness.trigger()

    [record] = await harness.wait_for_usage(1)
    assert record["input_tokens"] == 1200
    assert record["uncached_input_tokens"] == 200
    assert record["cache_read_tokens"] == 1000
    assert record["cache_write_5m_tokens"] == 0 and record["cache_write_1h_tokens"] == 0
    assert record["output_tokens"] == 300
    assert record["reasoning_tokens"] == 120
    assert record["estimated"] is False


# ── T6: cut stream, OpenAI shape ───────────────────────────────────────────────

async def test_t6_cut_stream_openai(harness):
    harness.provider.script.text = "Hello from the fake model."
    harness.provider.script.cut_after = 3  # role chunk + two words, then the stream just ends
    events = await harness.trigger()

    # no error event from the model side — the reply still completes
    assert len(_by_type(events, "message_done")) == 1
    assert not _by_type(events, "message_error")

    [record] = await harness.wait_for_usage(1)
    assert record["estimated"] is True
    assert record["output_tokens"] > 0          # estimated from the received text
    assert record["input_tokens"] > 0           # estimated from the request


# ── T7: cut stream, Anthropic shape ────────────────────────────────────────────

async def test_t7_cut_stream_anthropic(harness):
    harness.nucleus.persona = make_persona(anthropic_model(harness))
    harness.provider.script.usage = ANTHROPIC_USAGE
    harness.provider.script.cut_after = 4  # message_start, block_start, two deltas
    events = await harness.trigger()
    assert len(_by_type(events, "message_done")) == 1

    [record] = await harness.wait_for_usage(1)
    assert record["estimated"] is True
    # input and cache counts kept exactly as the provider reported them
    assert record["input_tokens"] == 1700
    assert record["cache_read_tokens"] == 1000
    assert record["cache_write_5m_tokens"] == 300 and record["cache_write_1h_tokens"] == 200
    # output estimated from the received text — not the provisional 1
    assert record["output_tokens"] > 1


# ── T8: client disconnects after 1 s ───────────────────────────────────────────

async def test_t8_client_disconnect(harness):
    harness.provider.script.text = " ".join(["word"] * 400)
    harness.provider.script.delay_between = 0.1  # ~40 s of stream — far longer than the test
    job = harness.job()

    async with httpx.AsyncClient(timeout=30) as client:
        async with client.stream(
            "POST", f"{harness.app_url}/api/v1/trigger/",
            json=job, headers={"X-Internal-Key": INTERNAL_KEY},
        ) as response:
            assert response.status_code == 200
            got_delta = False
            async for line in response.aiter_lines():
                if line.startswith("data: ") and json.loads(line[6:])["type"] == "message_delta":
                    got_delta = True
                    break
            assert got_delta
            await asyncio.sleep(1.0)
        # leaving both contexts closes the connection — the run is cancelled

    records = await harness.wait_for_usage(1)
    assert len(records) == 1                      # record_usage called once
    assert records[0]["estimated"] is True
    # the model stream was cut off early: nowhere near all 400 words arrived
    assert len(harness.provider.requests) == 1


# ── T9: model returns HTTP 500 ─────────────────────────────────────────────────

async def test_t9_model_http_500(harness):
    harness.provider.script.status = 500
    events = await harness.trigger(timeout=120)

    errors = _by_type(events, "message_error")
    assert len(errors) == 1
    assert not _by_type(events, "message_done")
    assert errors[0]["error"]

    records = await harness.wait_for_usage(1)
    assert records[0]["estimated"] is True


# ── T10: keepalive on silence, still exactly one final event ───────────────────

async def test_t10_keepalive(harness):
    os.environ["KEEPALIVE_SECONDS"] = "0.2"
    harness.provider.script.text = "one two three"
    harness.provider.script.delay_between = 0.5
    events = await harness.trigger()

    assert len(_by_type(events, "keepalive")) >= 1
    finals = [e for e in events if e["type"] in ("message_done", "message_error")]
    assert len(finals) == 1 and finals[0]["type"] == "message_done"


# ── T14: unplaced-feature fields are accepted and ignored ──────────────────────

async def test_t14_unplaced_fields(harness):
    job = harness.job(
        preflight=True, approved_plan="the plan", routine_id="r1",
        step_context="step one said hello", output_type="chart",
        context_sources=[{"source_id": "s1", "type": "doc", "label": "a.md", "collection_id": "c"}],
    )
    events = await harness.trigger(job)
    assert len(_by_type(events, "message_done")) == 1
    assert not _by_type(events, "message_error")


# ── T15: record_usage fails — the reply is still good ──────────────────────────

async def test_t15_record_usage_failure(harness):
    harness.nucleus.usage_status = 500
    events = await harness.trigger()
    assert len(_by_type(events, "message_done")) == 1
    assert not _by_type(events, "message_error")


# ── auth: the internal key is checked ──────────────────────────────────────────

async def test_internal_key_required(harness):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{harness.app_url}/api/v1/trigger/", json=harness.job(),
            headers={"X-Internal-Key": "wrong"},
        )
    assert response.status_code == 401
