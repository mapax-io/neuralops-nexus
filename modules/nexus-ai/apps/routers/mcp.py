"""
MCP connection check -- nexus-nucleus -> nexus-ai.

POST /api/v1/mcp/verify/ opens the server exactly the way a persona run
would (same transport builder as the runner) and lists its tools. It always
answers 200 with a result: `ok`, a `code` the UI can act on, and a message
written for the person looking at the form. A failed probe is a result, not
an HTTP error -- only a bad payload or a bad key is.
"""

from __future__ import annotations

import asyncio
import logging
import time

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security.api_key import APIKeyHeader
from pydantic import BaseModel, Field
from pydantic_ai.mcp import FastMCPClient

from apps.core.config import settings
from apps.implementations.agents.mcp_transport import build_transport
from apps.schemas.trigger import MCPServerConfig

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["mcp"])

_api_key_header = APIKeyHeader(name="X-Internal-Key", auto_error=False)


def _verify_key(key: str = Depends(_api_key_header)):
    if key != settings.INTERNAL_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid internal API key")
    return key


# A probe is interactive -- someone is watching a spinner -- so a server's
# own (possibly generous) per-call timeout is capped here.
MAX_PROBE_SECONDS = 30


class MCPToolOut(BaseModel):
    name: str
    description: str = ""


class MCPVerifyOut(BaseModel):
    ok: bool
    # ok | nothing_to_connect | unreachable | timeout | auth_required |
    # auth_rejected | not_mcp | command_not_found | error
    code: str
    error: str | None = None
    tools: list[MCPToolOut] = Field(default_factory=list)
    latency_ms: int | None = None


def _chain(exc: BaseException) -> list[BaseException]:
    """Every exception behind `exc`: causes, contexts and group members."""
    out: list[BaseException] = []
    seen: set[int] = set()
    stack = [exc]
    while stack:
        e = stack.pop()
        if id(e) in seen:
            continue
        seen.add(id(e))
        out.append(e)
        if isinstance(e, BaseExceptionGroup):
            stack.extend(e.exceptions)
        if e.__cause__:
            stack.append(e.__cause__)
        if e.__context__:
            stack.append(e.__context__)
    return out


def classify_error(exc: BaseException, server: MCPServerConfig) -> tuple[str, str]:
    """A code the UI can branch on, and a message for the person reading it."""
    stdio = server.transport == "stdio"
    for e in _chain(exc):
        text = str(e)
        low = text.lower()
        if isinstance(e, httpx.HTTPStatusError):
            status = e.response.status_code
            if status == 401:
                return "auth_required", "The server asked for credentials (HTTP 401)."
            if status == 403:
                return "auth_rejected", "The server rejected the credentials (HTTP 403)."
            if status == 404:
                return "not_mcp", "The address answered with HTTP 404 -- that path isn't an MCP endpoint. Many servers use /mcp or /sse."
            return "not_mcp", f"The address answered with HTTP {status}, not as an MCP server."
        if stdio and (isinstance(e, FileNotFoundError) or "no such file" in low or "not found" in low):
            return "command_not_found", "The command couldn't be started -- it wasn't found on the NeuralOps server. Check the program name and that it's installed there."
        if isinstance(e, (httpx.ConnectError, ConnectionRefusedError)) or any(
            m in low for m in ("connection refused", "name or service not known", "nodename nor servname", "getaddrinfo", "network is unreachable", "all connection attempts failed", "connect call failed")
        ):
            return "unreachable", "Nothing answered at that address -- check the URL (host, port, http vs https) and that the server is running."
        if isinstance(e, (httpx.ReadTimeout, httpx.ConnectTimeout, TimeoutError)):
            return "timeout", "The server didn't answer in time -- it may be down, or the address may be wrong."
        if "401" in text or "unauthorized" in low:
            return "auth_required", "The server asked for credentials (HTTP 401)."
        if "403" in text or "forbidden" in low:
            return "auth_rejected", "The server rejected the credentials (HTTP 403)."
        if any(m in low for m in ("session terminated", "invalid json", "expecting value", "not a valid", "unexpected content type", "text/html")):
            return "not_mcp", "The address answered, but not like an MCP server -- check the path (many servers use /mcp or /sse) and the transport."
    short = str(exc).strip().splitlines()[0][:200] if str(exc).strip() else exc.__class__.__name__
    return "error", f"Couldn't connect: {short}"


@router.post("/mcp/verify/", response_model=MCPVerifyOut)
async def verify(server: MCPServerConfig, _: str = Depends(_verify_key)) -> MCPVerifyOut:
    cfg = build_transport(server)
    if cfg is None:
        return MCPVerifyOut(ok=False, code="nothing_to_connect", error="Give the server a URL or a command first.")
    timeout = max(1, min(server.timeout_seconds or MAX_PROBE_SECONDS, MAX_PROBE_SECONDS))
    started = time.monotonic()
    try:
        async with asyncio.timeout(timeout):
            async with FastMCPClient(cfg) as client:
                tools = await client.list_tools()
    except TimeoutError:
        return MCPVerifyOut(ok=False, code="timeout", error=f"No answer within {timeout} seconds -- the address may be wrong, or the server is down.")
    except Exception as exc:  # noqa: BLE001 -- every failure is a result here
        code, message = classify_error(exc, server)
        log.info("[mcp] verify %s failed (%s): %s", server.name, code, exc)
        return MCPVerifyOut(ok=False, code=code, error=message)
    return MCPVerifyOut(
        ok=True,
        code="ok",
        tools=[MCPToolOut(name=t.name, description=t.description or "") for t in tools],
        latency_ms=int((time.monotonic() - started) * 1000),
    )
