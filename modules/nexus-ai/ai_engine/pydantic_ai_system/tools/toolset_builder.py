"""
ToolsetBuilder — turns the loaded set into harness/pydantic-ai capability
objects (§3.2's class, landed in tools/ per the §1.5 structure). The ONLY
class on the items-3+1+2 path that touches framework objects (dependency rule 2).

Namespacing uses the framework's own PrefixTools (verified on pinned 2.55):
each MCP capability is wrapped so its tool names arrive as <slug>__<name> —
exactly the catalog's model_name. Per-server narrowing uses MCP(allowed_tools=).

Item 2 additions (2026-10-12):
  - every capability gets an EXPLICIT id — the native's canonical key, or
    "prefixed-<server_id>" for MCP wrappers — because tool defs carry
    capability_id and the ApprovalGate maps tools back to sources through it;
  - filesystem/shell REQUIRE a workspace on the run (trial E finding b):
    a LocalWorkspace is added, rooted at the capability_config's
    root_dir/cwd. Nucleus's project provisioning writes the project folder
    there (/nexus/projects/<slug> — CapabilityInternal docstring); absent,
    the root falls back to "." exactly as 0.8.0's FileSystem default did
    (item 22 "stays as-is");
  - the ApprovalGate capability is appended last, built from ApprovalPolicy
    (persona.tool_levels + the topic's clearances) and the source map.

ToolSearch (item 2 decision 4, trial F 2026-10-13): ALL eligible capabilities
are built, not only the loaded ones; the gate hides tools outside the topic's
set (defer_loading) and ToolSearch(strategy="keywords") lets the model
discover them — their first use then asks the person once.

stdio MCP servers are NOT built in this pass: the pinned MCP(local=...) shape
is unverified for argv lists — flagged in the doc. HTTP/SSE servers are fully
supported.
"""
from __future__ import annotations

import inspect
import logging

from pydantic_ai.capabilities import (
    MCP,
    LocalWorkspace,
    PrefixTools,
    Thinking,
    ToolSearch,
    WebFetch,
    WebSearch,
)
from pydantic_ai_harness import ClearToolResults, DeduplicateFileReads, SummarizingCompaction, TieredCompaction
from pydantic_ai_harness.filesystem import FileSystem
from pydantic_ai_harness.shell import Shell

from ai_engine.core.specs import LoadedSet, PersonaSpec, ToolCatalogEntry
from ai_engine.pydantic_ai_system.tools.approval_gate import ApprovalGate
from ai_engine.pydantic_ai_system.tools.approval_policy import ApprovalPolicy, ToolSource
from ai_engine.pydantic_ai_system.tools.registry import normalize_key, server_slug

log = logging.getLogger(__name__)

_NATIVE_BUILDERS = {
    "filesystem": FileSystem,
    "shell": Shell,
    "web_search": WebSearch,
    "web_fetch": WebFetch,
    "thinking": Thinking,
}

# Natives that refuse to run without a workspace (harness require_workspace,
# verified 2026-10-12 on pinned 0.55: FileSystem.before_run, Shell.before_run).
_NEEDS_WORKSPACE = {"filesystem", "shell"}


class UnsupportedToolSourceError(ValueError):
    pass


class ToolsetBuilder:
    def build(self, loaded: LoadedSet, catalog: list[ToolCatalogEntry],
              persona: PersonaSpec, *, interactive: bool = True,
              clearances: frozenset[str] | set[str] = frozenset(),
              compaction_target: int | None = None) -> list:
        loaded_ids = set(loaded.tool_ids)
        eligible_ids = {entry.tool_id for entry in catalog}
        capabilities: list = []
        sources: dict[str, ToolSource] = {}

        # ── natives — every ELIGIBLE one; the gate hides the unloaded ──────
        configs = _native_configs(persona)
        workspace_root: str | None = None
        for key, config in configs.items():
            if key not in eligible_ids:
                continue  # explicitly off — out of the catalog entirely
            builder = _NATIVE_BUILDERS.get(key)
            if builder is None:
                log.warning("unknown native capability %r — skipped", key)
                continue
            kwargs = _accepted_kwargs(builder, config)
            kwargs["id"] = key  # canonical id → tool defs carry it (gate mapping)
            capabilities.append(builder(**kwargs))
            sources[key] = ToolSource(kind="native", cap_key=key, source_id=key)
            if key in _NEEDS_WORKSPACE and workspace_root is None:
                workspace_root = config.get("root_dir") or config.get("cwd")

        if any(k in _NEEDS_WORKSPACE and k in eligible_ids for k in configs):
            # 0.8.0 parity (item 22 "stays as-is"): root_dir defaulted to ".".
            # Provisioned personas carry the project folder in the config.
            if not workspace_root:
                log.warning("filesystem/shell without a configured root — using '.' (0.8.0 default)")
                workspace_root = "."
            capabilities.insert(0, LocalWorkspace(workspace_root))

        # ── external MCP servers (http/sse) — every eligible server ────────
        for server in persona.mcp_servers:
            sid = str(server.get("id"))
            # the server's ELIGIBLE tools (catalog); the gate narrows to loaded
            whole_server = f"mcp:{sid}" in eligible_ids
            tool_names = [t.split("/", 1)[1] for t in eligible_ids
                          if t.startswith(f"mcp:{sid}/")]
            if not whole_server and not tool_names:
                continue
            if not server.get("url"):
                # stdio: unverified MCP(local=…) shape on the pinned version —
                # refused loudly rather than wired wrong (doc, item 3 Open)
                raise UnsupportedToolSourceError(
                    f"stdio MCP server {server.get('name')!r} is not supported yet"
                )
            mcp = MCP(
                url=server["url"],
                id=sid,
                authorization_token=_bearer_token(server),
                allowed_tools=tool_names or None,  # None = whole server
            )
            slug = server_slug(server.get("name") or sid)
            # PrefixTools joins names as f"{prefix}_{name}" (trial E, 2026-10-12,
            # pinned 2.55) — so "{slug}_" yields the catalog's "{slug}__{tool}".
            wrapper_id = f"prefixed-{sid}"
            capabilities.append(PrefixTools(mcp, prefix=f"{slug}_", id=wrapper_id))
            sources[wrapper_id] = ToolSource(kind="mcp", cap_key=f"mcp:{sid}",
                                             source_id=sid, slug=slug)

        # ── the gate, then ToolSearch (item 2, decision 4) ─────────────────
        if capabilities:
            policy = ApprovalPolicy(persona.tool_levels, clearances)
            catalog_index = {entry.tool_id: entry for entry in catalog}
            something_hidden = bool(eligible_ids - loaded_ids)
            capabilities.append(ApprovalGate(
                policy, sources, catalog_index, interactive=interactive,
                loaded_ids=loaded_ids if something_hidden else None,
            ))
            if something_hidden:
                # "keywords" = the local, provider-independent strategy —
                # pinned behaviour verified in trial F; native strategies can
                # be revisited per provider later without a design change.
                capabilities.append(ToolSearch(strategy="keywords"))
            if compaction_target is not None:
                # Item 16 (§4.1): mid-run growth → compaction tiers 1→2→3,
                # 0.8.0's order kept, only the target fixed to the run's budget.
                capabilities.append(TieredCompaction(
                    tiers=[
                        DeduplicateFileReads(file_key=_read_file_key),   # 1: lossless
                        ClearToolResults(max_fraction=0.9, keep_pairs=5),  # 2: evict, don't summarize (0.8.0's numbers)
                        SummarizingCompaction(max_fraction=0.9),         # 3: history, last resort
                    ],
                    target_tokens=compaction_target,
                ))
        return capabilities


def _read_file_key(call) -> str | None:
    """Tier 1's dedup key — 0.8.0's read_file-only rule, kept (§4.1 notes it
    needs revisiting when graph/DuckDB results flow through)."""
    if call.tool_name.endswith("read_file"):
        try:
            import json as _json
            args = call.args if isinstance(call.args, dict) else _json.loads(call.args or "{}")
            return str(args.get("path")) if args.get("path") else None
        except (ValueError, TypeError):
            return None
    return None


def _native_configs(persona: PersonaSpec) -> dict[str, dict]:
    configs: dict[str, dict] = {}
    for row in persona.capabilities:
        for raw_key, config in (row.get("capability_config") or {}).items():
            configs[normalize_key(raw_key)] = dict(config or {})
    return configs


def _accepted_kwargs(builder, config: dict) -> dict:
    """Pass only kwargs the pinned class accepts — nucleus config may carry
    legacy keys (e.g. protected_patterns) newer classes renamed."""
    params = inspect.signature(builder.__init__).parameters
    accepted = {k: v for k, v in config.items() if k in params}
    dropped = set(config) - set(accepted)
    if dropped:
        log.info("%s: dropped unsupported config keys %s", builder.__name__, sorted(dropped))
    return accepted


def _bearer_token(server: dict) -> str | None:
    """Same rule as 0.8.0 (legacy nucleus_client): oauth2 servers send the USER
    access token under token_env_var; static servers send client_secret."""
    secrets = server.get("secrets") or {}
    if server.get("auth_type") == "oauth2":
        return secrets.get(server.get("token_env_var") or "OAUTH_ACCESS_TOKEN")
    return secrets.get("client_secret")
