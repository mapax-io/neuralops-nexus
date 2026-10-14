"""
A REAL MCP server for the dial test (pinned mcp 2.x) — two tools:

    search(query)        annotated readOnlyHint=True  → "MCP-RESULT: <query>"
    create_issue(title)  no annotations               → "created: <title>"

Served over streamable HTTP (the transport our MCPServerInternal rows use) by
the same ServedApp the other fakes use. This is the instrument that closes
Layer 1's "no server was ever dialed" gap: pydantic-ai's MCP capability dials
THIS, lists its tools live, and executes against it.
"""
from __future__ import annotations

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations


def make_mcp_app():
    server = MCPServer("fake-github")

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def search(query: str) -> str:
        """Search the fake code base."""
        return f"MCP-RESULT: {query}"

    @server.tool()
    def create_issue(title: str) -> str:
        """Open an issue (a write — no readOnlyHint on purpose)."""
        return f"created: {title}"

    return server.streamable_http_app(stateless_http=True)
