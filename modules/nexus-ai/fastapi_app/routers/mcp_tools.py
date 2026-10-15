"""
Step 6 (docs/NUCLEUS-REVAMP.md, handoff change 6) — list a live MCP server's
tools.

POST /api/v1/mcp/tools/ {url, bearer_token?} → {"tools": [{name, one_line,
read_only}]}. Nucleus calls this when an admin attaches/saves an external MCP
server, and from the "Refresh tools" button; the answer lands on the server
row and later ships back to triggers as MCPServerInternal.tools (the stored
catalog the approval policy reads).

read_only comes ONLY from the server's own readOnlyHint annotation; a tool
without one answers null, and nucleus treats null as a write (asks first) —
the safe default the owner settled.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from fastapi_app.routers.trigger import _verify_key

router = APIRouter(prefix="/api/v1", tags=["mcp"])

DIAL_TIMEOUT_SECONDS = 20


class ToolListRequest(BaseModel):
    url: str
    bearer_token: str | None = None


class ToolOut(BaseModel):
    name: str
    one_line: str = ""
    read_only: bool | None = None


class ToolListResponse(BaseModel):
    tools: list[ToolOut]


def _dial_imports():
    """The pinned mcp 2.x client pieces (verified live against the installed
    package, 2026-10-15): streamable_http_client(url, *, http_client=None, …)
    yields (read_stream, write_stream); headers/auth travel on a pre-built
    httpx2.AsyncClient passed as http_client. Imported lazily so a package
    layout shift surfaces as the 502's reason, not an import crash at boot."""
    import httpx2  # noqa: PLC0415 — the mcp 2.x client's own HTTP library
    from mcp import ClientSession  # noqa: PLC0415
    from mcp.client.streamable_http import streamable_http_client  # noqa: PLC0415
    return ClientSession, streamable_http_client, httpx2


@router.post("/mcp/tools/", response_model=ToolListResponse)
async def list_mcp_tools(req: ToolListRequest, _: str = Depends(_verify_key)) -> ToolListResponse:
    """One dial: initialize, list tools, hang up. Any failure — unreachable,
    refused auth, not an MCP server — is one answer: 502 with the reason, so
    nucleus can show it verbatim next to the Refresh button."""
    headers = {"Authorization": f"Bearer {req.bearer_token}"} if req.bearer_token else {}
    try:
        ClientSession, streamable_http_client, httpx2 = _dial_imports()
        async with httpx2.AsyncClient(headers=headers, timeout=DIAL_TIMEOUT_SECONDS) as http_client:
            async with streamable_http_client(req.url, http_client=http_client) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.list_tools()
    except Exception as exc:  # noqa: BLE001 — every dial failure is the same 502 + why
        raise HTTPException(status_code=502,
                            detail=f"could not list tools: {type(exc).__name__}: {exc}")

    tools: list[ToolOut] = []
    for tool in result.tools:
        annotations = getattr(tool, "annotations", None)
        read_only = getattr(annotations, "readOnlyHint", None) if annotations else None
        description = (tool.description or "").strip()
        one_line = description.splitlines()[0][:200] if description else ""
        tools.append(ToolOut(name=tool.name, one_line=one_line, read_only=read_only))
    return ToolListResponse(tools=tools)
