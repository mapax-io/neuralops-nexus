"""
Budget and BudgetFitter — item 16 (§4.1), the SELECTION half.

    input_budget = context_window − max_output_tokens − loop_headroom

Two numbers, structurally apart (§4.1): target (~70% of budget — what the
prompt is trimmed to before the run, and what compaction compacts down to)
and trigger (~90% — where mid-run compaction fires). The gap is what lets the
tool loop grow between compactions.

Selection and compaction are different mechanisms: this class is selection —
"do not put it in if it will not fit" — applied BEFORE the run. Mid-run growth
(tool results) is compaction's job (the TieredCompaction capability, wired in
ToolsetBuilder with target_tokens=budget.target).

Framework-free (dependency rule 1): the token estimator is injected — the
factory passes pydantic_ai_system's wrapper around the harness estimator.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from typing import Callable

from ai_engine.core.specs import ModelSpec, PromptPlan

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Budget:
    input_budget: int
    target: int    # trim/compact down to this
    trigger: int   # compaction fires above this


def budget_for(spec: ModelSpec, loop_headroom: int, target_pct: int, trigger_pct: int,
               max_output_tokens: int) -> Budget:
    """The run's budget from the MODEL's window and the PERSONA's output cap —
    two separate numbers, never one field (§4.1: reading max_output_tokens as
    the window is the live 0.8.0 defect this exists to bury)."""
    input_budget = max(1, spec.context_window - max_output_tokens - loop_headroom)
    return Budget(
        input_budget=input_budget,
        target=max(1, input_budget * target_pct // 100),
        trigger=max(1, input_budget * trigger_pct // 100),
    )


class BudgetFitter:
    """Trim a prompt plan to the model's budget (§1.5 catalog, L2).

    Order (§4.1's protection list): OLD HISTORY is dropped first, oldest
    message first; then sections below the persona prompt's priority (today:
    the tool catalog). NEVER dropped: the current user message, the persona
    prompt / project brief, attached files (none yet — Layer 3)."""

    def __init__(self, estimate: Callable[[str], int]) -> None:
        self._estimate = estimate

    def fit(self, plan: PromptPlan, budget: Budget) -> PromptPlan:
        est = self._estimate
        fixed = sum(est(s.text) for s in plan.instructions) + est(plan.message)
        history_costs = [est(m.text) for m in plan.history]
        total = fixed + sum(history_costs)
        if total <= budget.target:
            return plan

        # 1) drop old history, oldest first
        history = list(plan.history)
        costs = list(history_costs)
        while history and total > budget.target:
            total -= costs.pop(0)
            dropped = history.pop(0)
            log.info("budget: dropped history message (%d chars) — over target", len(dropped.text))
        if total <= budget.target:
            return replace(plan, history=tuple(history))

        # 2) drop droppable sections (below the persona prompt's priority)
        sections = list(plan.instructions)
        for section in sorted((s for s in sections if s.priority < 90), key=lambda s: s.priority):
            sections.remove(section)
            total -= est(section.text)
            log.info("budget: dropped section %r — over target", section.kind)
            if total <= budget.target:
                break
        if total > budget.target:
            # protected content alone exceeds the target: §4.1's escape valve
            # (indexing, items 33/34) is the real answer — never truncate it here.
            log.warning("budget: protected content (%d tokens) exceeds target %d — sent anyway",
                        total, budget.target)
        return replace(plan, history=tuple(history), instructions=tuple(sections))
