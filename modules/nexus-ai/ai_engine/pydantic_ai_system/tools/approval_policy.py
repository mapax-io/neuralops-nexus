"""
ApprovalPolicy — item 2's policy, pure and I/O-free (testable like HistoryPolicy).

Ported from 0.8.0's `level_for` (nexus-ai-legacy/apps/managers/approvals.py),
re-keyed on the item 3 catalog ids, plus the 2026-10-12 decisions (§1.3
item 2, 5–7):
  - read tools run automatically, never ask;
  - write tools ask EVERY time — no "always allow" escape;
  - an MCP tool with unknown read/write nature (no stored read_only, no
    readOnlyHint) asks, unless the topic's clearance list says it is a read
    (the one "always allow" left; stored by nucleus next to topic_tools).
Explicit persona `tool_levels` win over all defaults, as at 0.8.0 — an admin's
deliberate per-tool setting, not the approval card's button.

Level keys honoured (the same keying 0.8.0's levels already support):
  "<capability>/<tool>"  one native tool     e.g. "filesystem/write_file"
  "<capability>"         a whole native      e.g. "filesystem"
  "mcp:<sid>/<tool>"     one MCP tool        (= the catalog tool_id)
  "mcp:<sid>"            a whole MCP server
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Mapping

from ai_engine.core.specs import ToolCatalogEntry

LEVELS = ("auto", "ask", "off")

# Native tools that change something outside the conversation. Everything else
# a native capability offers only reads. Names are the pinned harness 0.55
# toolsets (verified 2026-10-12): FileSystem and Shell.
ACTING_NATIVE_TOOLS: dict[str, set[str]] = {
    "shell": {"run_command", "start_command", "stop_command"},
    "filesystem": {"write_file", "edit_file", "create_directory"},
}

PREVIEW_CHARS = 300

# The texts the model sees when a call did NOT run — each states that plainly,
# because told only "declined" a model has answered with invented output
# (0.8.0's wording, kept).
REFUSED_UNATTENDED = (
    "{tool} needs a person's approval, and nobody can give one in this run "
    "(a schedule or an unattended job). Say what you would have done instead."
)
DENIED = (
    "The person declined this call. It did not run and nothing changed. Say so "
    "plainly and do not show any output for it; explain, or find another way."
)


def args_preview(args: object) -> str:
    """One short line of what the call would do — for the approval card,
    never the raw object. pydantic-ai hands tool args as a JSON string."""
    if isinstance(args, str):
        text = args
    else:
        try:
            text = json.dumps(args, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            text = str(args)
    return text if len(text) <= PREVIEW_CHARS else text[: PREVIEW_CHARS - 1] + "…"


@dataclass(frozen=True)
class ToolSource:
    """What ToolsetBuilder knows about one capability it built — the gate maps
    a run-time ToolDefinition back to the catalog through this."""

    kind: str        # "native" | "mcp"
    cap_key: str     # "filesystem" | "shell" | ... | "mcp:<server_id>"
    source_id: str   # native key, or the MCP server id
    slug: str = ""   # MCP only: the model-name prefix ("github")


class ApprovalPolicy:
    def __init__(self, tool_levels: Mapping[str, str] | None = None,
                 clearances: frozenset[str] | set[str] = frozenset()) -> None:
        self._levels = dict(tool_levels or {})
        # topic clearances: catalog tool_ids the topic marked "treat as read"
        # (decision 6 — only meaningful for MCP tools with read_only=None)
        self._clearances = frozenset(clearances)

    # ── catalog time (ToolRegistry) ────────────────────────────────────────
    def catalog_level(self, entry: ToolCatalogEntry) -> str:
        """Only an EXPLICIT level can be 'off' — defaults never hide a tool.
        Used by ToolRegistry to drop off tools from the catalog entirely
        (never searchable, never loadable)."""
        for key in self._level_keys(entry.tool_id, entry.source_kind, entry.source_id):
            level = self._levels.get(key)
            if level in LEVELS:
                return level
        return "auto" if entry.source_kind == "native" else "default"

    # ── run time (ApprovalGate) ────────────────────────────────────────────
    def runtime_level(self, *, tool_name: str, source: ToolSource | None,
                      entry: ToolCatalogEntry | None, metadata: Mapping | None) -> str:
        """auto | ask | off for one tool the model may call right now."""
        if source is None:
            # not a tool we built (future: ToolSearch's own tool, output tools)
            return "auto"
        if source.kind == "native":
            for key in (f"{source.cap_key}/{tool_name}", source.cap_key):
                level = self._levels.get(key)
                if level in LEVELS:
                    return level
            acting = tool_name in ACTING_NATIVE_TOOLS.get(source.cap_key, ())
            return "ask" if acting else "auto"
        # MCP: strip the model-name prefix back to the server's own tool name
        base = tool_name.removeprefix(f"{source.slug}__") if source.slug else tool_name
        tool_id = f"mcp:{source.source_id}/{base}"
        for key in (tool_id, source.cap_key):
            level = self._levels.get(key)
            if level in LEVELS:
                return level
        read_only = entry.read_only if entry is not None else None
        if read_only is True:
            return "auto"
        if read_only is None:
            annotations = (metadata or {}).get("annotations") or {}
            if annotations.get("readOnlyHint") is True:
                return "auto"
            if tool_id in self._clearances:
                return "auto"  # the topic cleared this unlabeled tool as a read
        return "ask"  # a known write, or unknown and uncleared

    @staticmethod
    def _level_keys(tool_id: str, source_kind: str, source_id: str) -> tuple[str, ...]:
        if source_kind == "mcp":
            return (tool_id, f"mcp:{source_id}")
        return (tool_id,)
