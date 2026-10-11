"""
T11 / T12 — the cost formula, exact to the Decimal. Prices are TEST FIXTURES,
not real prices. O1: production pricing happens in nucleus; this pins the
formula nucleus must implement.
"""
from __future__ import annotations

import dataclasses
from datetime import datetime, timezone
from decimal import Decimal

from ai_engine.core.billing import Prices, compute_cost
from ai_engine.core.specs import UsageRecord


def _record(**counts) -> UsageRecord:
    base = dict(
        company_id="c1", project_id="pr1", topic_id="t1", persona_id="p1",
        user_id="u1", message_id="m1", job_id="j1", kind="chat_reply",
        model_config_id="mc1", provider="anthropic", model_id="fake", role="STANDARD",
        provider_response_id=None, input_tokens=0, uncached_input_tokens=0,
        cache_read_tokens=0, cache_write_5m_tokens=0, cache_write_1h_tokens=0,
        output_tokens=0, reasoning_tokens=0, finish_reason="stop", estimated=False,
        called_at=datetime.now(timezone.utc),
    )
    base.update(counts)
    return UsageRecord(**base)


def test_t11_cost_anthropic_numbers():
    """T4's numbers, fixture prices 3.00 / 0.30 / 3.75 / 6.00 / 15.00 → 0.007725 exactly."""
    record = _record(
        input_tokens=1700, uncached_input_tokens=200, cache_read_tokens=1000,
        cache_write_5m_tokens=300, cache_write_1h_tokens=200, output_tokens=300,
    )
    prices = Prices(
        input=Decimal("3.00"), cache_read=Decimal("0.30"),
        cache_write_5m=Decimal("3.75"), cache_write_1h=Decimal("6.00"),
        output=Decimal("15.00"),
    )
    assert compute_cost(record, prices) == Decimal("0.007725")


def test_t12_cost_openai_numbers():
    """T5's numbers, fixture prices 2.50 / 1.25 / 10.00 → 0.00475 exactly.
    Reasoning is inside output_tokens — priced once, never added on top."""
    record = _record(
        input_tokens=1200, uncached_input_tokens=200, cache_read_tokens=1000,
        output_tokens=300, reasoning_tokens=120,
    )
    prices = Prices(input=Decimal("2.50"), cache_read=Decimal("1.25"), output=Decimal("10.00"))
    assert compute_cost(record, prices) == Decimal("0.00475")


def test_cost_is_decimal_never_float():
    record = _record(input_tokens=1, uncached_input_tokens=1, output_tokens=1)
    cost = compute_cost(record, Prices(input=Decimal("0.1"), output=Decimal("0.2")))
    assert isinstance(cost, Decimal)
    assert cost == Decimal("0.1") / Decimal(1_000_000) + Decimal("0.2") / Decimal(1_000_000)
