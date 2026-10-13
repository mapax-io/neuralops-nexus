"""
ApprovalGate — the capability that applies ApprovalPolicy at run time (item 2).

Mechanism (trial E, 2026-10-12, pinned 2.55): prepare_tools receives EVERY
capability's ToolDefinitions and may rewrite them —
  - level off  → the tool is dropped (defence in depth: off tools are already
    out of the catalog, but a server-level MCP load could still surface one);
  - level ask, interactive run → kind='unapproved': the run PAUSES with
    DeferredToolRequests instead of executing (the pause/resume path);
  - level ask, unattended run → the tool stays callable but
    before_tool_execute refuses it with 0.8.0's "nobody can approve" text via
    SkipToolExecution, so the model hears it did not run and answers on.

The gate maps a ToolDefinition back to its source through capability_id:
ToolsetBuilder gives natives their canonical key as id ("filesystem") and MCP
wrappers "prefixed-<server_id>" (verified 2026-10-12: capability_id arrives on
every tool def).
"""
from __future__ import annotations

from dataclasses import replace
from typing import Mapping

from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.exceptions import SkipToolExecution

from ai_engine.core.specs import ToolCatalogEntry
from ai_engine.pydantic_ai_system.tools.approval_policy import (
    REFUSED_UNATTENDED,
    ApprovalPolicy,
    ToolSource,
)


class ApprovalGate(AbstractCapability):
    def __init__(self, policy: ApprovalPolicy,
                 sources: Mapping[str, ToolSource],
                 catalog_index: Mapping[str, ToolCatalogEntry],
                 interactive: bool = True) -> None:
        self._policy = policy
        self._sources = dict(sources)          # capability_id → ToolSource
        self._catalog = dict(catalog_index)    # tool_id → entry
        self._interactive = interactive
        # Filled by prepare_tools (which runs before any model call): the
        # model-facing name → capability_id, read live by EventMapper and the
        # pause builder to label approval cards with their source.
        self.tool_capability_ids: dict[str, str] = {}

    async def prepare_tools(self, ctx, tool_defs):
        out = []
        for tool_def in tool_defs:
            self.tool_capability_ids[tool_def.name] = tool_def.capability_id or ""
            level = self._level(tool_def)
            if level == "off":
                continue
            if level == "ask" and self._interactive:
                tool_def = replace(tool_def, kind="unapproved")
            out.append(tool_def)
        return out

    async def before_tool_execute(self, ctx, *, call, tool_def, args):
        if not self._interactive and self._level(tool_def) == "ask":
            raise SkipToolExecution(REFUSED_UNATTENDED.format(tool=call.tool_name))
        return args

    # ── mapping one run-time tool back to the policy's world ───────────────
    def _level(self, tool_def) -> str:
        source = self._sources.get(tool_def.capability_id or "")
        entry = None
        if source is not None and source.kind == "mcp":
            base = tool_def.name.removeprefix(f"{source.slug}__") if source.slug else tool_def.name
            entry = self._catalog.get(f"mcp:{source.source_id}/{base}")
        return self._policy.runtime_level(
            tool_name=tool_def.name, source=source, entry=entry,
            metadata=tool_def.metadata,
        )
