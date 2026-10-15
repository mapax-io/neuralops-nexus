"""
Pricing — Step 1 (docs/NUCLEUS-REVAMP.md). Turns the engine's token counts
into an ESTIMATED cost, as exact Decimal, frozen onto the usage row at insert.

Price lookup order (owner's ruling):
  1. the admin-typed OVERRIDE on the ModelConfig row (any of the three set)
  2. the local catalog (ModelPrice, refreshed from an online source)
  3. nothing known → cost stays NULL; the tokens still count.

Everything money is ESTIMATED by design — "prices not confirmed" — the UI
label rides price_source/prices_used, never a recomputation.

Cost formula (engine semantics, its tests T4/T5/T11/T12 define the counts):
  input_tokens INCLUDES cache read + write; output INCLUDES reasoning. So:
    cost = uncached_input * input_price
         + cache_read * cached_price
         + (cache_write_5m + cache_write_1h) * input_price   (approximation:
           the catalog carries three numbers; providers price cache WRITES
           near the input rate — fine for an estimate, and the label says so)
         + output * output_price
  all per-million prices, Decimal end to end — never float (engine rule kept).
"""
from __future__ import annotations

import logging
from decimal import Decimal

logger = logging.getLogger(__name__)

MILLION = Decimal(1_000_000)


def _dec(value) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except Exception:  # noqa: BLE001 — a broken price must not break billing
        return None


def prices_for(model_config_id: str, provider: str, model_id: str):
    """Return (input, cached, output, source) — Decimals per million, or
    (None, None, None, "") when nothing is known. Never raises."""
    from nucleus.models import ModelConfig, ModelPrice

    # 1) the admin's override on the config row
    if model_config_id:
        row = ModelConfig.objects.filter(id=model_config_id).first()
        if row is not None:
            over = (_dec(row.price_input_per_million),
                    _dec(row.price_cached_per_million),
                    _dec(row.price_output_per_million))
            if any(p is not None for p in over):
                inp, cached, out = over
                # an untyped cached price defaults to the input price; untyped
                # fields default to 0 — the admin typed SOMETHING on purpose
                inp = inp if inp is not None else Decimal(0)
                return (inp,
                        cached if cached is not None else inp,
                        out if out is not None else Decimal(0),
                        "override")

    # 2) the refreshed catalog
    row = ModelPrice.objects.filter(provider=provider, model_id=model_id).first()
    if row is None:
        # openai_compatible endpoints often serve a well-known model id —
        # try the bare model id under any provider before giving up
        row = ModelPrice.objects.filter(model_id=model_id).first()
    if row is not None:
        inp = _dec(row.input_per_million) or Decimal(0)
        cached = _dec(row.cached_per_million)
        out = _dec(row.output_per_million) or Decimal(0)
        return (inp, cached if cached is not None else inp, out, "catalog")

    return (None, None, None, "")


def cost_of(record: dict, inp: Decimal, cached: Decimal, out: Decimal) -> Decimal:
    """The estimate, exact Decimal arithmetic on the engine's counts."""
    uncached = Decimal(int(record.get("uncached_input_tokens") or 0))
    cache_read = Decimal(int(record.get("cache_read_tokens") or 0))
    writes = Decimal(int(record.get("cache_write_5m_tokens") or 0)
                     + int(record.get("cache_write_1h_tokens") or 0))
    output = Decimal(int(record.get("output_tokens") or 0))
    return (uncached * inp + cache_read * cached + writes * inp + output * out) / MILLION


def price_record(record: dict) -> dict:
    """Fill cost / prices_used / price_source for one engine record dict.
    Returns the fields to store; never raises (billing must not break saves)."""
    try:
        inp, cached, out, source = prices_for(
            record.get("model_config_id") or "",
            record.get("provider") or "",
            record.get("model_id") or "",
        )
        if source == "":
            return {"cost": None, "prices_used": None, "price_source": ""}
        return {
            "cost": cost_of(record, inp, cached, out),
            "prices_used": {"input_per_million": str(inp),
                            "cached_per_million": str(cached),
                            "output_per_million": str(out)},
            "price_source": source,
        }
    except Exception:  # noqa: BLE001
        logger.exception("[pricing] failed for %s:%s — storing tokens without cost",
                         record.get("provider"), record.get("model_id"))
        return {"cost": None, "prices_used": None, "price_source": ""}
