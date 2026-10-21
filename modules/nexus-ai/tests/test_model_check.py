"""
Layer 2, item 40 — the model check endpoint, ported
(docs/NEXUS-AI-REVAMP.md §4.6; POST /api/v1/models/check/ kept so nucleus's
Register/Edit model dialogs work unchanged; the fingerprint persistence half
of item 40 is nucleus work).
"""
from __future__ import annotations

import httpx
import pytest

from conftest import INTERNAL_KEY

pytestmark = pytest.mark.asyncio


async def _check(harness, payload: dict) -> dict:
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{harness.app_url}/api/v1/models/check/",
            json=payload, headers={"X-Internal-Key": INTERNAL_KEY},
        )
        assert response.status_code == 200
        return response.json()


async def test_mc1_working_model_checks_ok(harness):
    """Item 40 — a reachable model with a good key answers ok with its latency.
    The check builds the model with the SAME ModelFactory a persona run uses
    and streams one tiny call — passing means a persona on this model will run."""
    result = await _check(harness, {
        "provider": "openai", "model_id": "fake-model",
        "api_key": "k", "api_base": harness.provider_url + "/v1",
    })
    assert result["ok"] is True
    assert isinstance(result["latency_ms"], int) and result["latency_ms"] >= 0


async def test_mc2_unsupported_provider_is_named(harness):
    """Item 40 — an unknown provider is refused up front, with its own code.
    No call is attempted; error_code='unsupported_provider' tells nucleus to
    word it as a configuration problem, not a key problem."""
    result = await _check(harness, {"provider": "banana", "model_id": "x"})
    assert result["ok"] is False
    assert result["error_code"] == "unsupported_provider"


async def test_mc4_deepseek_rides_the_openai_wire(harness):
    """Walkthrough finding (2026-10-19) — nucleus offers 'deepseek' as a
    provider, so the worker must run it: DeepSeek speaks the OpenAI protocol,
    and the factory routes it through the OpenAI client (api.deepseek.com by
    default; an explicit api_base — here the fake provider — wins)."""
    result = await _check(harness, {
        "provider": "deepseek", "model_id": "deepseek-chat",
        "api_key": "k", "api_base": harness.provider_url + "/v1",
    })
    assert result["ok"] is True
    assert isinstance(result["latency_ms"], int) and result["latency_ms"] >= 0


async def test_mc3_dead_endpoint_is_a_model_failure(harness):
    """Item 40 — an unreachable endpoint reports model_failure, never a 500.
    The check answers 200 with ok=false and the raw error for nucleus to word —
    a broken model must never break the endpoint that tests models."""
    result = await _check(harness, {
        "provider": "openai", "model_id": "dead",
        "api_key": "k", "api_base": "http://127.0.0.1:9/v1",
    })
    assert result["ok"] is False
    assert result["error_code"] in ("model_failure", "error")
    assert result["error"]
