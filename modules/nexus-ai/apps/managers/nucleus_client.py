"""
apps/managers/nucleus_client.py

Small HTTP client for the calls nexus-ai makes BACK into nexus-nucleus
before it can build a prompt -- resolving a persona's model/system-prompt/
MCP config, and fetching conversation history. Same auth pattern already
used elsewhere in this direction (see pydantic_ai_runner.py:_post_ai_request_log),
just the reverse of the nucleus -> nexus-ai calls in routers/trigger.py.

This is where the prompt-quality decisions nexus-nucleus used to make now
live: how much history to pull (HISTORY_DEPTH, a nexus-ai setting, not a
nucleus one), which past replies are "good enough" to show the model, and
mapping raw sender_type into the "user"/"assistant" role an LLM expects.
"""
from __future__ import annotations

import logging
from threading import local

import httpx
from pydantic_ai.capabilities import MCP

from apps.core.config import settings
import shlex
from apps.schemas.trigger import HistoryMessage, MCPArgs, ModelConfig, PersonaConfig, PersonaCapabilities
from fastmcp.client.transports import StdioTransport

log = logging.getLogger(__name__)

_VISUAL_TYPES = {"chart", "table", "diagram", "html", "form"}


async def resolve_persona(persona_id: str) -> PersonaConfig:
    """
    Fetch a persona's model + system prompt + MCP server config from
    nexus-nucleus. Raises on failure (network error, 404 persona not
    found, 400 persona has no prompt) -- same failure shape as an LLM
    call erroring out: the stream just ends without a message_done, and
    nucleus's placeholder message stays PENDING. Not a new failure mode,
    consistent with how AgenticManager already handles a runner error.
    """
    url = f"{settings.NEXUS_NUCLEUS_URL}/api/v1/internal/personas/{persona_id}/"
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            url, headers={"X-Internal-API-Key": settings.INTERNAL_API_KEY},
        )
        response.raise_for_status()
    data = response.json()

    model_data = data.get("model")
    model = ModelConfig(
        provider=model_data["provider"] if model_data else "litellm",
        model_id=model_data["model_id"] if model_data else settings.LLM_MODEL,
        api_key=model_data.get("api_key") if model_data else None,
        max_tokens=model_data.get("max_tokens", 4096) if model_data else 4096,
        temperature=model_data.get("temperature", 0.7) if model_data else 0.7,
    )
    
    if data['capabilities']:
        capabilities = PersonaCapabilities.model_validate(data['capabilities'][0]['capability_config'])
    else:
        capabilities = PersonaCapabilities()

    log.info(data['capabilities'])
    log.info(data["mcp_servers"])
    _mcp_servers = data.get('mcp_servers')
    mcp_servers = []
    if _mcp_servers:
        for _mcp_server in _mcp_servers:
            network_url = _mcp_server.get('url')
            local_cmd = _mcp_server.get('command')
            secrets = _mcp_server.get('secrets') or {}
            
            if network_url:
                # Route A: HTTP Server
                mcp_servers.append(MCPArgs(
                    url=network_url,
                    authorization_token=secrets.get('client_secret')
                ))
            elif local_cmd:
                # Route B: Local Server
                parts = shlex.split(local_cmd)
                mcp_servers.append(MCPArgs(
                    url=None,
                    command=parts[0],
                    args=parts[1:],
                    env=secrets  # FastMCP will safely load these as subprocess env vars
                ))

    return PersonaConfig(
        id=data["id"],
        name=data["name"],
        system_prompt=(data.get("prompt") or {}).get("system_prompt", ""),
        model=model,
        mcp_servers=mcp_servers,
        capabilities=capabilities,
    )


async def fetch_history(topic_id: str, exclude_message_id: str | None = None) -> list[HistoryMessage]:
    """
    Fetch and shape conversation history for a trigger.

    Role-mapping and filtering both happen here, not in nexus-nucleus:
      - a "system" notification (e.g. "Session closed.") is excluded
        entirely, not folded into "assistant" the way it used to be
      - an "assistant" reply that claims to be HTML but doesn't actually
        look like HTML is dropped -- probably a broken/incomplete render
      - a reply whose output_type was visual (chart/table/diagram/html/
        form) but ended up rendered as plain text is dropped too --
        usually means the visual generation failed and fell back
    """
    url = f"{settings.NEXUS_NUCLEUS_URL}/api/v1/internal/topics/{topic_id}/history/"
    params: dict = {"limit": settings.HISTORY_DEPTH}
    if exclude_message_id:
        params["exclude_message_id"] = exclude_message_id

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            url, params=params,
            headers={"X-Internal-API-Key": settings.INTERNAL_API_KEY},
        )
        response.raise_for_status()
    raw = response.json()

    history: list[HistoryMessage] = []
    for m in raw:
        content = (m.get("content") or "").strip()
        if not content:
            continue

        sender_type = m.get("sender_type")
        if sender_type == "human":
            role = "user"
        elif sender_type == "persona":
            role = "assistant"
        else:
            continue  # "system" notifications aren't a persona's own words

        if role == "assistant":
            render_as = m.get("render_as", "text")
            output_type_val = m.get("output_type", "text")
            if render_as == "html" and not (
                content.startswith("<!DOCTYPE") or content.startswith("<html")
            ):
                continue
            if output_type_val in _VISUAL_TYPES and render_as == "text":
                continue

        history.append(HistoryMessage(
            role=role,
            content=m.get("content") or "",
            sender_name=m.get("sender_name"),
        ))

    return history
