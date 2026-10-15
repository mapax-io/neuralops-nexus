"""
Step 6 (docs/NUCLEUS-REVAMP.md) — the two service endpoints nucleus's front
doors call: POST /search/messages/ (chat search after switch-over + the
gateway's search_memory) and POST /mcp/tools/ (stored tool lists, change 6).
"""
from __future__ import annotations

import httpx
import pytest

from conftest import INTERNAL_KEY
from fake_mcp import make_mcp_app
from fake_provider import ServedApp

pytestmark = pytest.mark.asyncio

HASH = {"provider": "hash", "model_id": "hash-768"}


async def _post(harness, path, payload, key=INTERNAL_KEY):
    async with httpx.AsyncClient(timeout=60.0) as client:
        return await client.post(f"{harness.app_url}{path}", json=payload,
                                 headers={"X-Internal-Key": key} if key else {})


async def _embed_message(harness, message_id, project_id, content, n=0):
    payload = {
        "message_id": message_id, "company_id": "cs1", "sequence": n,
        "topic_id": "ts1", "channel_id": "ch1", "project_id": project_id,
        "sender_id": "u1", "sender_name": "N", "sender_type": "human",
        "content": content, "created_at": "2026-10-15T00:00:00Z",
        "embedder": HASH,
    }
    response = await _post(harness, "/api/v1/embed/message/", payload)
    assert response.status_code == 200, response.text


async def test_s6a_search_messages_ranks_across_projects(harness, vector_url):
    """Step 6 — POST /search/messages/ answers the 0.8.0 chat-search contract.
    Two messages in two different projects; one query names one of them; the
    endpoint searches BOTH projects, answers best-first, and only message rows
    (kinds is pinned to message). This is the endpoint chat/search.py's
    semantic_ids() has been calling against the legacy engine — the rebuilt
    module now serves it, closing a silent switch-over degradation."""
    await _embed_message(harness, "s6-m1", "s6p1", "we picked pgbouncer for connection pooling", 1)
    await _embed_message(harness, "s6-m2", "s6p2", "the deploy always runs on fridays", 2)
    response = await _post(harness, "/api/v1/search/messages/", {
        "company_id": "cs1", "query": "pgbouncer connection pooling",
        "top_k": 5, "project_ids": ["s6p1", "s6p2"],
    })
    assert response.status_code == 200, response.text
    hits = response.json()["hits"]
    assert hits and hits[0]["message_id"] == "s6-m1"
    assert all(set(h) == {"message_id", "score"} for h in hits)


async def test_s6b_search_requires_the_key_and_tolerates_empty(harness, vector_url):
    """Step 6 — the search endpoint is internal-key gated and never invents hits.
    No key = 401 (same second lock as every endpoint); a project with no index
    answers an empty hits list, not an error — nucleus falls back to its
    literal search on empty."""
    response = await _post(harness, "/api/v1/search/messages/",
                           {"company_id": "cs1", "query": "x", "project_ids": ["nope"]},
                           key=None)
    assert response.status_code == 401
    response = await _post(harness, "/api/v1/search/messages/",
                           {"company_id": "cs1", "query": "x", "project_ids": ["never-indexed"]})
    assert response.status_code == 200
    assert response.json() == {"hits": []}


async def test_s6c_mcp_tools_lists_names_lines_and_read_hints(harness):
    """Step 6 / change 6 — POST /mcp/tools/ dials a REAL server and labels reads.
    The fake MCP server (the same one the Layer 1 dial test uses) answers two
    tools: search carries readOnlyHint=true → read_only true; create_issue has
    no annotations → read_only null (nucleus treats null as a write — asks
    first); one_line is the description's first line."""
    served = ServedApp(make_mcp_app()).start()
    try:
        response = await _post(harness, "/api/v1/mcp/tools/", {"url": served.url + "/mcp"})
        assert response.status_code == 200, response.text
        tools = {t["name"]: t for t in response.json()["tools"]}
        assert tools["search"]["read_only"] is True
        assert tools["create_issue"]["read_only"] in (None, False)
        assert tools["search"]["one_line"].startswith("Search")
    finally:
        served.stop()


async def test_s6d_mcp_tools_unreachable_is_one_clear_502(harness):
    """Step 6 / change 6 — a dead server is a 502 with the reason, never a hang.
    nucleus shows the detail verbatim next to the Refresh button; the admin
    reads why instead of staring at a spinner."""
    response = await _post(harness, "/api/v1/mcp/tools/",
                           {"url": "http://127.0.0.1:9/mcp"})
    assert response.status_code == 502
    assert "could not list tools" in response.json()["detail"]
