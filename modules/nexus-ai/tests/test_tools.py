"""
Layer 1, items 3+1 — the tool catalog and the permitted/loaded set
(docs/NEXUS-AI-REVAMP.md §1.3 "Item 3" / "Item 1" entries, settled 2026-10-12).

Unit tests of ToolRegistry (pure, like HistoryPolicy) plus acceptance tests
through the running service: loaded schemas reach the provider request, the
catalog section is stable, topic_tools pins the set.
"""
from __future__ import annotations

import json

import pytest

from ai_engine.core.nucleus_client import persona_from
from ai_engine.pydantic_ai_system.tools.registry import ToolRegistry
from conftest import openai_model
from fake_nucleus import make_persona
from fastapi_app.contracts.trigger import TriggerJob

pytestmark = pytest.mark.asyncio


def _mcp_server(sid: str, name: str, tools: list[dict] | None) -> dict:
    server = {
        "id": sid, "name": name, "server_type": "custom", "transport": "http",
        "url": f"https://{sid}.example.com/mcp", "command": None, "config": {},
        "secrets": {}, "is_first_party": False, "embed_output": False,
        "needs_reauth": False, "auth_type": "static_secrets",
        "token_env_var": "OAUTH_ACCESS_TOKEN",
    }
    if tools is not None:
        server["tools"] = tools
    return server


def _persona_spec(mcp_servers: list[dict] | None = None, capabilities: list[dict] | None = None,
                  model: dict | None = None):
    data = make_persona(model or {
        "id": "m1", "name": "fake", "provider": "openai", "model_id": "fake",
        "qualified_id": "openai:fake", "api_base": None, "api_key": None,
        "context_window": 100_000, "supports_tools": True,
        "supports_streaming": True, "supports_vision": False,
    })
    if mcp_servers is not None:
        data["mcp_servers"] = mcp_servers
    if capabilities is not None:
        data["capabilities"] = capabilities
    return persona_from(data, company_id="c1", project_id="pr1")


def _job(**overrides) -> TriggerJob:
    base = dict(job_id="j1", msg_id="m1", persona_id="p1", topic_id="t1",
                user_message_id="um1", message="q")
    base.update(overrides)
    return TriggerJob(**base)


# ── Item 3: the catalog ─────────────────────────────────────────────────────────

def test_l1_catalog_namespaces_same_named_tools():
    """Item 3 — two servers exposing the same tool name stay distinct.
    Catalog ids are mcp:<server_id>/<tool>; model-facing names are prefixed
    with the server slug (github__search vs monday__search) — two same-named
    tools can never collide or shadow each other."""
    persona = _persona_spec(mcp_servers=[
        _mcp_server("s-gh", "GitHub", [{"name": "search", "description": "Search code", "read_only": True}]),
        _mcp_server("s-mon", "Monday.com", [{"name": "search", "description": "Search boards", "read_only": True}]),
    ])
    catalog = ToolRegistry().catalog_for(persona)
    mcp_entries = [e for e in catalog if e.source_kind == "mcp"]
    assert {e.tool_id for e in mcp_entries} == {"mcp:s-gh/search", "mcp:s-mon/search"}
    names = {e.model_name for e in mcp_entries}
    assert len(names) == 2 and all("__search" in n for n in names)


def test_l1_catalog_builds_without_network():
    """Item 3 — the catalog is built from nucleus's stored tool lists alone.
    ToolRegistry is pure: given a persona whose servers carry `tools`, the
    catalog exists with ZERO network calls (no server is dialed)."""
    persona = _persona_spec(mcp_servers=[
        _mcp_server("s1", "GitHub", [
            {"name": "search", "description": "Search code", "read_only": True},
            {"name": "create_issue", "description": "Open an issue", "read_only": False},
        ]),
    ])
    catalog = ToolRegistry().catalog_for(persona)  # would raise/hang if it dialed
    assert [e.tool_id for e in catalog if e.source_kind == "mcp"] == \
        ["mcp:s1/search", "mcp:s1/create_issue"]
    assert [e.read_only for e in catalog if e.source_kind == "mcp"] == [True, False]


def test_l1_catalog_server_without_stored_tools_is_one_entry():
    """Item 3 — today's nucleus (no `tools` list yet) still catalogs the server.
    A server without a stored tool list becomes ONE server-level entry
    (mcp:<id>), so the persona keeps working before nucleus change (6) lands;
    its real tools appear at dial time."""
    persona = _persona_spec(mcp_servers=[_mcp_server("s1", "GitHub", None)])
    catalog = ToolRegistry().catalog_for(persona)
    [entry] = [e for e in catalog if e.source_kind == "mcp"]
    assert entry.tool_id == "mcp:s1" and entry.read_only is None


def test_l1_catalog_natives_from_capability_config():
    """Item 3 — native capabilities are catalogued from capability_config.
    Keys arrive as display names or field names ('Web Search' / 'web_search');
    both normalize to the level-keying ids 0.8.0 already uses, with one-liners
    and read-only hints from the static table."""
    persona = _persona_spec(capabilities=[{
        "id": "cap1", "name": "defaults",
        "capability_config": {"Filesystem": {"root_dir": "."}, "Web Search": {"local": "duckduckgo"},
                              "shell": {"cwd": "."}},
    }])
    catalog = ToolRegistry().catalog_for(persona)
    by_id = {e.tool_id: e for e in catalog}
    assert set(by_id) == {"filesystem", "web_search", "shell"}
    assert by_id["web_search"].read_only is True
    assert by_id["filesystem"].one_line  # a human line exists for the prompt


def test_l1_catalog_empty_persona():
    """Item 3 — a persona with no tools has an empty catalog.
    No sources → no catalog entries → the reply is a plain Layer 0 reply."""
    assert ToolRegistry().catalog_for(_persona_spec()) == []


# ── Item 1: the loaded set ──────────────────────────────────────────────────────

def test_l1_topic_tools_pin_the_loaded_set():
    """Item 1 — topic_tools in the job IS the loaded set, verbatim.
    When nucleus sends the topic's stored set, exactly those ids are loaded —
    narrow-once-and-hold — regardless of how many tools are eligible."""
    persona = _persona_spec(mcp_servers=[
        _mcp_server("s1", "GitHub", [{"name": "search", "description": "s", "read_only": True},
                                     {"name": "create_issue", "description": "c", "read_only": False}]),
    ])
    job = _job(topic_tools=["mcp:s1/search"])
    loaded = ToolRegistry().tools_for(persona, job)
    assert loaded.tool_ids == ("mcp:s1/search",)


def test_l1_first_reply_loads_all_eligible_capped():
    """Item 1 — first reply in a topic (no topic_tools, no router yet, L1):
    all eligible tools are loaded, capped by MAX_LOADED_TOOLS, in catalog
    order; the rest stay catalog-only."""
    many = [{"name": f"tool{i}", "description": "d", "read_only": True} for i in range(20)]
    persona = _persona_spec(mcp_servers=[_mcp_server("s1", "Big", many)])
    loaded = ToolRegistry(max_loaded_tools=5).tools_for(persona, _job())
    assert len(loaded.tool_ids) == 5
    assert loaded.tool_ids == tuple(f"mcp:s1/tool{i}" for i in range(5))


def test_l1_unknown_topic_tool_ids_are_dropped():
    """Item 1 — a stored id that is no longer eligible is dropped, not fatal.
    (A server was detached since the set was stored: the reply still runs with
    what remains — same spirit as drift handling.)"""
    persona = _persona_spec(mcp_servers=[
        _mcp_server("s1", "GitHub", [{"name": "search", "description": "s", "read_only": True}]),
    ])
    loaded = ToolRegistry().tools_for(persona, _job(topic_tools=["mcp:s1/search", "mcp:gone/x"]))
    assert loaded.tool_ids == ("mcp:s1/search",)


# ── Acceptance: through the running service ─────────────────────────────────────

async def test_l1_loaded_native_schema_reaches_the_request(harness):
    """Items 3+1 — a loaded native tool's schema is in the provider request.
    Persona has the web_search capability; the request body's tools carry its
    schema, and the instructions carry the catalog section."""
    persona = make_persona(openai_model(harness))
    persona["capabilities"] = [{"id": "cap1", "name": "defaults",
                                "capability_config": {"web_search": {"local": "duckduckgo"}}}]
    harness.nucleus.persona = persona
    events = await harness.trigger()
    assert [e for e in events if e["type"] == "message_done"]

    body = harness.provider.requests[-1]
    assert "tools" in body and len(body["tools"]) >= 1
    assert "search" in json.dumps(body["tools"]).lower()
    # the catalog section is part of the (stable) instructions
    assert "Tools available in this conversation" in json.dumps(body["messages"])


async def test_l1_catalog_section_is_stable_across_turns(harness):
    """Item 1 / item 15 — the catalog section is byte-identical across turns.
    Two triggers in the same topic produce the same system content and the
    same tools array — the cache prefix survives."""
    persona = make_persona(openai_model(harness))
    persona["capabilities"] = [{"id": "cap1", "name": "defaults",
                                "capability_config": {"web_search": {"local": "duckduckgo"}}}]
    harness.nucleus.persona = persona
    await harness.trigger()
    await harness.trigger(harness.job(msg_id="msg-2", job_id="job-2"))

    first, second = harness.provider.requests[-2], harness.provider.requests[-1]
    sys1 = [m for m in first["messages"] if m["role"] == "system"]
    sys2 = [m for m in second["messages"] if m["role"] == "system"]
    assert sys1 == sys2
    assert first.get("tools") == second.get("tools")


async def test_l1_toolless_persona_is_plain_layer0(harness):
    """Items 3+1 — no tools configured → the Layer 0 contract is untouched.
    No tools field pollution, no catalog section, T1-shape stream."""
    events = await harness.trigger()
    assert [e for e in events if e["type"] == "message_done"]
    body = harness.provider.requests[-1]
    assert not body.get("tools")
    assert "Tools available" not in json.dumps(body["messages"])
