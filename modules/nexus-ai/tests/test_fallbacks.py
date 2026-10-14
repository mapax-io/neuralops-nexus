"""
Layer 2, item 12 — fallback models, opt-in per persona
(docs/NEXUS-AI-REVAMP.md §1.3 Layer 2 decision 1; built 2026-10-13).

0.8.0's own retry, ported: candidates in order, a whole fresh stream per
candidate, never a switch after the first token reached the reader, the reply
labelled "answered by X (fallback)". No fallbacks configured = Layer 0's clean
failure, unchanged (T9 already proves that).
"""
from __future__ import annotations

import pytest

from conftest import openai_model
from fake_nucleus import make_model, make_persona

pytestmark = pytest.mark.asyncio

DEAD = "http://127.0.0.1:9/v1"  # connection refused, fails before any token


async def test_fb1_fallback_answers_and_is_labelled(harness):
    """Item 12 — the primary dies before a token: the fallback answers, labelled.
    Primary model points at a dead endpoint; the configured fallback answers
    normally; message_done says answered_by_model='<name> (fallback)'; TWO
    usage records land — the failed primary (estimated, its own model id) and
    the fallback's real one."""
    persona = make_persona(
        make_model("openai", DEAD, config_id="m-primary", model_id="dead-model"),
        fallback_models=[openai_model(harness, config_id="m-fb", model_id="fb-model")],
    )
    harness.nucleus.persona = persona
    harness.provider.script.text = "Fallback answered this."
    events = await harness.trigger()

    types = [e["type"] for e in events]
    assert types[-1] == "message_done" and "message_error" not in types
    [done] = [e for e in events if e["type"] == "message_done"]
    assert "Fallback answered" in done["content"]
    assert done["answered_by_model"] == "Fake openai (fallback)"

    records = await harness.wait_for_usage(2)
    assert records[0]["model_id"] == "dead-model" and records[0]["estimated"] is True
    assert records[1]["model_id"] == "fb-model" and records[1]["estimated"] is False


async def test_fb2_all_candidates_dead_is_one_clean_error(harness):
    """Item 12 — primary AND fallback dead: one clean message_error, both billed.
    Nothing retries forever: the candidate list is exhausted, the stream ends
    with exactly one error event, and BOTH failed attempts land as estimated
    records (a failed call's input is never free — T9's rule, per candidate)."""
    persona = make_persona(
        make_model("openai", DEAD, config_id="m-primary", model_id="dead-model"),
        fallback_models=[make_model("openai", DEAD, config_id="m-fb", model_id="dead-fb")],
    )
    harness.nucleus.persona = persona
    events = await harness.trigger()

    types = [e["type"] for e in events]
    assert types[-1] == "message_error"
    assert types.count("message_error") == 1 and "message_done" not in types
    records = await harness.wait_for_usage(2)
    assert [r["model_id"] for r in records] == ["dead-model", "dead-fb"]
    assert all(r["estimated"] for r in records)


async def test_fb3_no_fallbacks_fails_clean_unchanged(harness):
    """Item 12 — the default (no fallbacks) is Layer 0's behaviour, untouched.
    A persona without fallback_models and a dead model → exactly one
    message_error, one estimated record, nothing retried behind anyone's back."""
    harness.nucleus.persona = make_persona(
        make_model("openai", DEAD, config_id="m-primary", model_id="dead-model"),
    )
    events = await harness.trigger()
    types = [e["type"] for e in events]
    assert types[-1] == "message_error" and types.count("message_error") == 1
    records = await harness.wait_for_usage(1)
    assert len(records) == 1 and records[0]["model_id"] == "dead-model"
