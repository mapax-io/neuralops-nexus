"""
ToolRegistry — items 3 + 1 (docs/NEXUS-AI-REVAMP.md §1.3 entries, 2026-10-12).

catalog_for: every tool the persona could use, by name, from what nucleus sent
— PURE, zero network (the stored lists are the catalog; live lists apply at
dial time, in ToolsetBuilder's MCP connections).

tools_for: the topic's loaded set — job.topic_tools verbatim when nucleus sent
it (narrow-once-and-hold), else the Layer 1 first-reply rule: all eligible,
capped by MAX_LOADED_TOOLS, catalog order. Layer 2 replaces exactly that else-
branch with the router's tool_hints.
"""
from __future__ import annotations

import hashlib
import re

from ai_engine.core.specs import LoadedSet, PersonaSpec, ToolCatalogEntry
from ai_engine.pydantic_ai_system.tools.approval_policy import ApprovalPolicy
from fastapi_app.contracts.trigger import TriggerJob

# Native capabilities: id → (one line for the prompt catalog, read-only hint).
# Ids are the level keys 0.8.0 already uses.
NATIVE_TOOLS: dict[str, tuple[str, bool | None]] = {
    "filesystem": ("Read, list and write files in the project folder", None),
    "shell": ("Run shell commands in the project folder", None),
    "web_search": ("Search the web", True),
    "web_fetch": ("Fetch a web page and read it", True),
    "thinking": ("Think longer before answering", True),
}


def normalize_key(key: str) -> str:
    """capability_config keys arrive as display names ('Web Search') or field
    names ('web_search') — both map to the canonical id."""
    return re.sub(r"[\s\-]+", "_", key.strip().lower())


def server_slug(name: str) -> str:
    """The model-facing prefix for a server's tools (github__search)."""
    slug = re.sub(r"[^a-z0-9]+", "_", (name or "").lower()).strip("_")
    return slug or "mcp"


class ToolRegistry:
    def __init__(self, max_loaded_tools: int = 12) -> None:
        self.max_loaded_tools = max_loaded_tools

    # ── item 3: the catalog ────────────────────────────────────────────────
    def catalog_for(self, persona: PersonaSpec) -> list[ToolCatalogEntry]:
        entries: list[ToolCatalogEntry] = []

        # natives — from the internal capability rows' capability_config
        for row in persona.capabilities:
            for raw_key in (row.get("capability_config") or {}):
                key = normalize_key(raw_key)
                one_line, read_only = NATIVE_TOOLS.get(key, (f"The {key} capability", None))
                entries.append(ToolCatalogEntry(
                    tool_id=key, model_name=key, source_id=str(row.get("id", key)),
                    source_kind="native", one_line=one_line, read_only=read_only,
                ))

        # external MCP servers — from nucleus's stored tool lists (change 6)
        slugs: dict[str, str] = {}
        for server in persona.mcp_servers:
            sid = str(server.get("id"))
            slug = server_slug(server.get("name") or sid)
            if slug in slugs.values():
                slug = f"{slug}_{sid[:6]}"  # two servers with the same name
            slugs[sid] = slug
            tools = server.get("tools")
            if tools is None:
                # today's nucleus: no stored list yet — one server-level entry;
                # the real tools appear at dial time (item 3's live-list rule)
                entries.append(ToolCatalogEntry(
                    tool_id=f"mcp:{sid}", model_name=slug, source_id=sid,
                    source_kind="mcp",
                    one_line=f"Tools from the {server.get('name') or slug} server",
                    read_only=None,
                ))
                continue
            for tool in tools:
                entries.append(ToolCatalogEntry(
                    tool_id=f"mcp:{sid}/{tool['name']}",
                    model_name=f"{slug}__{tool['name']}",
                    source_id=sid, source_kind="mcp",
                    one_line=tool.get("description") or "",
                    read_only=tool.get("read_only"),
                ))
        # Item 2: an explicitly OFF tool leaves the catalog entirely — never
        # searchable, never loadable (defaults can't turn a tool off).
        policy = ApprovalPolicy(persona.tool_levels)
        return [e for e in entries if policy.catalog_level(e) != "off"]

    # ── item 1: the loaded set ─────────────────────────────────────────────
    def tools_for(self, persona: PersonaSpec, job: TriggerJob) -> LoadedSet:
        catalog = self.catalog_for(persona)
        eligible = [entry.tool_id for entry in catalog]
        if job.topic_tools is not None:
            # the stored set, verbatim; ids no longer eligible are dropped,
            # never fatal (a server was detached since the set was stored)
            loaded = tuple(t for t in job.topic_tools if t in set(eligible))
        else:
            # first reply in the topic, Layer 1: all eligible, capped.
            # Layer 2 replaces THIS branch with the router's tool_hints.
            loaded = tuple(eligible[: self.max_loaded_tools])
        return LoadedSet(tool_ids=loaded, catalog_hash=_catalog_hash(catalog))


def _catalog_hash(catalog: list[ToolCatalogEntry]) -> str:
    digest = hashlib.sha256()
    for entry in catalog:
        digest.update(f"{entry.tool_id}|{entry.model_name}|{entry.one_line}\n".encode())
    return digest.hexdigest()
