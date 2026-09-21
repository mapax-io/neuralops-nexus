"""
One way to close a tool call, for both runners.

tool_call_start says a persona reached for a tool; tool_call_end says how it
went -- name, outcome, duration and a clipped text preview -- so nucleus can
keep an activity trail and the reader can audit a run without the raw result.
"""
from __future__ import annotations

import time
from typing import Any

from apps.schemas.trigger import AgentEvent, AgentEventType, ToolResultData

TOOL_PREVIEW_CHARS = 600
TOOL_ERROR_CHARS = 300


def preview_of(content: Any) -> str | None:
    if content is None:
        return None
    text = content if isinstance(content, str) else str(content)
    return text[:TOOL_PREVIEW_CHARS]


def tool_end_event(msg_id: str, name: str, *, ok: bool, started_at: float, content: Any = None, error: str | None = None) -> AgentEvent:
    reason = (error or "")[:TOOL_ERROR_CHARS] if not ok else ""
    return AgentEvent(
        type=AgentEventType.TOOL_CALL_END,
        id=msg_id,
        tool_result=ToolResultData(
            name=name,
            ok=ok,
            duration_ms=max(0, int((time.monotonic() - started_at) * 1000)),
            preview=preview_of(content) if ok else None,
            error=reason or None,
        ),
    )


async def execute_mcp_tool(client, name: str, args: dict) -> tuple[str, bool]:
    """
    Run one MCP tool and return (text for the model, ok). The text is exactly
    what the LiteLLM loop has always appended as the tool message; ok is what
    the activity trail needs on top of it.
    """
    if client is None:
        return f"Tool '{name}' not found.", False
    try:
        result = await client.call_tool(name, args)
    except Exception as exc:
        return f"Tool error: {exc}", False
    items = result if isinstance(result, list) else getattr(result, "content", [result])
    content = "\n".join(item.text if hasattr(item, "text") else str(item) for item in items)
    is_error = getattr(result, "is_error", getattr(result, "isError", False))
    if is_error:
        return f"Error from tool: {content}", False
    return content, True
