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
    root_dir/cwd — absent, the build refuses loudly (item 22 wires the
    project folder properly);
  - the ApprovalGate capability is appended last, built from ApprovalPolicy
    (persona.tool_levels + the topic's clearances) and the source map.

stdio MCP servers are NOT built in this pass: the pinned MCP(local=...) shape
is unverified for argv lists — flagged in the doc. HTTP/SSE servers are fully
supported.
"""
from __future__ import annotations

import inspect
import logging

from pydantic_ai.capabilities import MCP, LocalWorkspace, PrefixTools, Thinking, WebFetch, WebSearch
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
              clearances: frozenset[str] | set[str] = frozenset()) -> list:
        loaded_ids = set(loaded.tool_ids)
        capabilities: list = []
        sources: dict[str, ToolSource] = {}

        # ── natives ────────────────────────────────────────────────────────
        configs = _native_configs(persona)
        workspace_root: str | None = None
        for key, config in configs.items():
            if key not in loaded_ids:
                continue
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

        if any(k in _NEEDS_WORKSPACE and k in loaded_ids for k in configs):
            if not workspace_root:
                # Refused loudly rather than crashing mid-run with the harness's
                # UserError — item 22 wires the project folder as the root.
                raise UnsupportedToolSourceError(
                    "filesystem/shell need a workspace root (capability_config "
                    "root_dir or cwd) — the project folder arrives with item 22"
                )
            capabilities.insert(0, LocalWorkspace(workspace_root))

        # ── external MCP servers (http/sse) ────────────────────────────────
        for server in persona.mcp_servers:
            sid = str(server.get("id"))
            # which of this server's tools are loaded?
            whole_server = f"mcp:{sid}" in loaded_ids
            tool_names = [t.split("/", 1)[1] for t in loaded_ids
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

        # ── the gate, last (item 2) ────────────────────────────────────────
        if capabilities:
            policy = ApprovalPolicy(persona.tool_levels, clearances)
            catalog_index = {entry.tool_id: entry for entry in catalog}
            capabilities.append(ApprovalGate(policy, sources, catalog_index,
                                             interactive=interactive))
        return capabilities


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
