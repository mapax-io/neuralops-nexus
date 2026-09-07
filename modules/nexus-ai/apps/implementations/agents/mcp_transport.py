"""
One place that turns an MCPServerConfig into what FastMCPClient accepts.

Shared by the agent runner (every persona run) and the connection check
(POST /api/v1/mcp/verify/), so a server that passes the check is a server
that runs -- the two can never drift apart on how a transport is built.
"""

from __future__ import annotations

import logging
import shlex

from fastmcp.client.transports import (
    SSETransport,
    StdioTransport,
    StreamableHttpTransport,
)

from apps.schemas.trigger import MCPServerConfig

log = logging.getLogger(__name__)

Transport = str | StdioTransport | SSETransport | StreamableHttpTransport


def build_transport(s: MCPServerConfig) -> Transport | None:
    """
    The transport for one server, or None when there is nothing to connect
    to (a stdio server with an empty command, a URL server with no URL).
    """
    if s.transport == "stdio":
        # shlex.split (not str.split) so quoted args survive intact --
        # e.g. a command like
        #   ssh -i ~/.ssh/key user@host "bash -c 'PATH=... npx ...'"
        # needs the quoted bash -c argument kept as ONE arg, not blown
        # apart on every space inside it. A naive .split() would mangle
        # exactly this shape, which is the standard way to reach a
        # remote stdio MCP server (e.g. npx @modelcontextprotocol/
        # server-filesystem) over SSH.
        cmd_parts = shlex.split(s.command or "")
        if not cmd_parts:
            return None
        # Built explicitly (not a bare {command, args} dict) so
        # s.secrets (e.g. GITHUB_PERSONAL_ACCESS_TOKEN, decrypted
        # by nucleus from MCPServer.secrets_encrypted) can be
        # passed as subprocess env -- the token never touches the
        # plain-text `command` string, and stdio servers don't
        # inherit this process's shell environment by default.
        return StdioTransport(
            command=cmd_parts[0],
            args=cmd_parts[1:],
            env=s.secrets or None,
        )

    # http | sse | streamable-http | websocket
    if not s.url:
        return None
    # OAuth2-authenticated servers need the access token sent
    # as a bearer header on every request -- StdioTransport
    # gets the whole `secrets` dict as subprocess env above,
    # but there's no equivalent "env" concept over HTTP/SSE.
    # Only the specific token_env_var key is forwarded here,
    # never the full secrets dict -- refresh_token/client_secret
    # must never leave nucleus and reach the remote MCP server.
    headers = None
    if s.auth_type == "oauth2":
        token = (s.secrets or {}).get(s.token_env_var)
        if token:
            headers = {"Authorization": f"Bearer {token}"}
        else:
            # needs_reauth already fails fast before this point when there's
            # no valid token -- reaching here with auth_type oauth2 and no
            # token means the token_env_var doesn't match what was actually
            # stored. Log and continue unauthenticated rather than silently
            # dropping the server.
            log.warning(
                "[runner] MCP server %s is oauth2 but has no "
                "token under '%s' -- connecting without auth.",
                s.name,
                s.token_env_var,
            )
    if headers is None:
        # No auth to attach -- pass the bare URL so FastMCPClient's own
        # URL-scheme dispatch keeps picking the transport (including ws://
        # websocket servers, which StreamableHttpTransport/SSETransport
        # don't handle).
        return s.url
    if s.transport == "sse":
        return SSETransport(s.url, headers=headers)
    return StreamableHttpTransport(s.url, headers=headers)
