"""
The cost formula, pinned (§1.3 Billing / §1.5 "Cost formula").

O1 resolution: nucleus owns the price table and prices each UsageRecord on
arrival — so production cost is computed THERE, not here. This module exists
so the formula itself is pinned in code with exact-number tests (T11/T12);
nucleus implements the same arithmetic.

All Decimal, never float. Prices are per million tokens.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ai_engine.core.specs import UsageRecord

_MILLION = Decimal(1_000_000)


@dataclass(frozen=True)
class Prices:
    """One model's prices per million tokens, each token type priced separately."""

    input: Decimal
    cache_read: Decimal = Decimal(0)
    cache_write_5m: Decimal = Decimal(0)
    cache_write_1h: Decimal = Decimal(0)
    output: Decimal = Decimal(0)


def compute_cost(record: UsageRecord, prices: Prices) -> Decimal:
    """
    cost = ( uncached_input * input
           + cache_read     * cache_read
           + cache_write_5m * cache_write_5m
           + cache_write_1h * cache_write_1h
           + output         * output ) / 1_000_000

    Cached tokens are never priced at the input rate; reasoning is never
    added on top of output (it is already inside output_tokens).
    """
    return (
        Decimal(record.uncached_input_tokens) * prices.input
        + Decimal(record.cache_read_tokens) * prices.cache_read
        + Decimal(record.cache_write_5m_tokens) * prices.cache_write_5m
        + Decimal(record.cache_write_1h_tokens) * prices.cache_write_1h
        + Decimal(record.output_tokens) * prices.output
    ) / _MILLION
