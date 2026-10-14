"""
UsageReader — every usage figure PER MODEL CALL from pydantic-ai's RequestUsage
(never the run total, never its best-effort cost), split into the priced token
types and flagged estimated by the §1.3 Billing rule.

Counting semantics (verified in the trial and re-verified on the pinned
2.55.0):
  - input_tokens is the WHOLE input, including cache read and cache write
  - output_tokens includes reasoning
  - uncached input = input_tokens − cache_read − cache_write
  - cache write 1h = cache_write_1h_tokens (undeclared field: absent means 0,
    details["ephemeral_1h_input_tokens"] is the cross-check); 5m = rest
  - estimated when: the run was cancelled, or finish_reason is empty, or
    input and output are both 0. Then: keep any input/cache counts the
    provider did send; estimate output from the text actually received;
    estimate input from the request when the provider sent none.
"""
from __future__ import annotations

import dataclasses
from typing import Sequence

from pydantic_ai.messages import ModelMessage, ModelResponse, ModelRequest, TextPart, UserPromptPart
from pydantic_ai_harness.compaction import estimate_token_count

from ai_engine.core.specs import UsageRecord


def estimate_tokens(text: str) -> int:
    """Token estimate for one piece of text — the harness estimator wrapped so
    framework-free code (BudgetFitter, item 16) can take it as an injected
    callable without importing the framework (dependency rule 1)."""
    if not text:
        return 0
    return estimate_token_count([ModelRequest(parts=[UserPromptPart(content=text)])])


class UsageReader:
    def read(
        self,
        response: ModelResponse | None,
        request_messages: Sequence[ModelMessage],
        received_text: str,
        cancelled: bool,
        base: UsageRecord,
    ) -> UsageRecord:
        usage = response.usage if response is not None else None
        finish_reason = response.finish_reason if response is not None else None
        provider_response_id = response.provider_response_id if response is not None else None

        input_tokens = usage.input_tokens if usage else 0
        cache_read = usage.cache_read_tokens if usage else 0
        cache_write = usage.cache_write_tokens if usage else 0
        output_tokens = usage.output_tokens if usage else 0
        details = (usage.details or {}) if usage else {}
        # undeclared fields: the provider code sets them only when reported
        cache_write_1h = (getattr(usage, "cache_write_1h_tokens", 0) if usage else 0) \
            or int(details.get("ephemeral_1h_input_tokens") or 0)
        reasoning = (getattr(usage, "output_reasoning_tokens", 0) if usage else 0) \
            or int(details.get("reasoning_tokens") or 0)

        estimated = bool(cancelled or not finish_reason or (input_tokens == 0 and output_tokens == 0))
        if estimated:
            # output: from the text actually received (provider counts here are
            # 0, or Anthropic's provisional 1 from the stream's first event)
            output_tokens = (
                estimate_token_count([ModelResponse(parts=[TextPart(content=received_text)])])
                if received_text else 0
            )
            reasoning = 0
            # input: only when the provider sent none at all
            if input_tokens == 0:
                input_tokens = estimate_token_count(list(request_messages))
                cache_read = cache_write = cache_write_1h = 0

        uncached = max(input_tokens - cache_read - cache_write, 0)
        cache_write_5m = max(cache_write - cache_write_1h, 0)

        return dataclasses.replace(
            base,
            provider_response_id=provider_response_id,
            input_tokens=input_tokens,
            uncached_input_tokens=uncached,
            cache_read_tokens=cache_read,
            cache_write_5m_tokens=cache_write_5m,
            cache_write_1h_tokens=cache_write_1h,
            output_tokens=output_tokens,
            reasoning_tokens=reasoning,
            finish_reason=finish_reason,
            estimated=estimated,
        )
