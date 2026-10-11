"""
MCPClient interface — every MCP transport implements this.
Supports stdio (local MCP servers) and SSE (remote MCP servers).
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class MCPClient(ABC):
    """Abstract MCP client."""

    @abstractmethod
    async def list_tools(self) -> list[dict]:
        """List all tools exposed by this MCP server."""
        ...

    @abstractmethod
    async def call_tool(self, tool_name: str, args: dict) -> str:
        """
        Call a tool on the MCP server.
        Returns the tool output as a string.
        """
        ...

    @abstractmethod
    async def close(self) -> None:
        """Clean up the connection."""
        ...
