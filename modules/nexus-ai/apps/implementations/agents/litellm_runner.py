"""
LiteLLM-based AgentRunner implementation.

Uses litellm.acompletion() directly for all providers — simpler and more
reliable than pydantic-ai model wrappers for the streaming use case.

Model routing via model_id prefix (LiteLLM convention):
    "openai/gpt-4o-mini"                    → OpenAI
    "anthropic/claude-haiku-4-5-20251001"   → Anthropic
    "azure/gpt-4"                            → Azure OpenAI
    "ollama/llama3"                          → Ollama (provider=local)

For M8 MCP integration: wrap with pydantic-ai Agent + mcp_servers here only.
"""

from __future__ import annotations

import logging
import time
import json
import contextlib
from typing import AsyncIterator

import httpx
import litellm
from fastmcp.client.transports import (
    StdioTransport,
    StreamableHttpTransport,
    SSETransport,
)
from pydantic_ai.mcp import FastMCPClient

from apps.interfaces.agent import AgentRunner
from apps.schemas.trigger import (
    PersonaConfig,
    TriggerJob,
    AgentEvent,
    AgentEventType,
    ToolCallData,
    ModelConfig,
)
from apps.core.config import settings

# Suppress litellm's verbose logging
litellm.suppress_debug_info = True

log = logging.getLogger(__name__)


class MCPReauthRequiredError(Exception):
    pass


class LiteLLMRunner(AgentRunner):
    """
    Streams LLM responses via LiteLLM (plain model) or pydantic-ai Agent (MCP).
    Receives the fully-assembled messages list from PromptBuilder and
    yields message_delta events.

    Routing:
        job.persona.mcp_servers is empty  → LiteLLM direct streaming (fast path)
        job.persona.mcp_servers non-empty → pydantic-ai Agent with MCP tools
    """

    async def run_stream(
        self,
        job: TriggerJob,
        messages: list[dict],
        persona: PersonaConfig,
        tools: list[dict] | None = None,
    ) -> AsyncIterator[AgentEvent]:
        # M8: persona has MCP servers — delegate to pydantic-ai agent runner
        if persona.mcp_servers:
            async for event in self._run_with_mcp(job, messages, persona, tools):
                yield event
            return

        # Default: LiteLLM direct streaming (unchanged from pre-M8)
        model_config = persona.model
        kwargs = _build_litellm_kwargs(model_config, messages)
        if tools:
            kwargs["tools"] = tools

        full_response = ""
        prompt_tokens = 0
        completion_tokens = 0
        status = "success"
        error_msg = None
        t0 = time.monotonic()

        # Buffer to accumulate streaming tool calls
        assembled_tool_calls: dict[int, dict] = {}

        try:
            response = await litellm.acompletion(**kwargs)
            async for chunk in response:  # type: ignore
                delta = chunk.choices[0].delta

                # 1. Handle normal text streaming
                if getattr(delta, "content", None):
                    full_response += delta.content
                    yield AgentEvent(
                        type=AgentEventType.DELTA,
                        id=job.msg_id,
                        delta=delta.content,
                    )

                # 2. Handle streaming tool calls
                if getattr(delta, "tool_calls", None):
                    for tc in delta.tool_calls:
                        idx = tc.index
                        if idx not in assembled_tool_calls:
                            assembled_tool_calls[idx] = {
                                "id": tc.id or f"call_{idx}",
                                "name": tc.function.name if tc.function else "",
                                "arguments": "",
                            }
                        if tc.function and tc.function.arguments:
                            assembled_tool_calls[idx]["arguments"] += (
                                tc.function.arguments
                            )
                # Accumulate usage from the final chunk (some providers send it there)
                if hasattr(chunk, "usage") and chunk.usage:
                    prompt_tokens = getattr(chunk.usage, "prompt_tokens", 0) or 0
                    completion_tokens = (
                        getattr(chunk.usage, "completion_tokens", 0) or 0
                    )

            # At the very end of the stream, yield any fully assembled tool calls!
            # The orchestrator (e.g. SwarmManager) will catch these.
            for tc in assembled_tool_calls.values():
                try:
                    args = json.loads(tc["arguments"] or "{}")
                except json.JSONDecodeError:
                    args = {}

                yield AgentEvent(
                    type=AgentEventType.TOOL_CALL_START,
                    id=job.msg_id,
                    tool_call=ToolCallData(name=tc["name"], args=args),
                )

        except Exception as exc:
            status = "error"
            error_msg = str(exc)
            log.error("[runner] litellm error for job %s: %s", job.job_id, exc)
            raise
        finally:
            latency_ms = int((time.monotonic() - t0) * 1000)
            await _post_ai_request_log(
                job=job,
                persona=persona,
                messages=messages,
                response=full_response,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                latency_ms=latency_ms,
                status=status,
                error=error_msg,
            )

    async def _run_with_mcp(
        self,
        job: TriggerJob,
        messages: list[dict],
        persona: "PersonaConfig",
        injected_tools: list[dict] | None = None,
    ) -> AsyncIterator[AgentEvent]:
        """
        Run the persona via litellm + FastMCPClient tool loop.

        Bypasses pydantic-ai Agent entirely — uses litellm directly (same as
        the fast path) so model routing works identically. FastMCPClient is
        used only to connect to MCP servers and execute tool calls.

        Loop: call LLM (non-stream) → if tool_calls → execute via MCP → repeat
              → final answer → yield as message_delta.
        """

        model_config = persona.model
        current_messages = list(messages)
        full_response = ""
        t0 = time.monotonic()
        status = "success"
        error_msg = None

        # Build MCP transport configs
        client_configs = []
        reauth = [s.name for s in persona.mcp_servers if s.needs_reauth]
        if reauth:
            names = ", ".join(reauth)
            raise MCPReauthRequiredError(
                f"The MCP server{'s' if len(reauth) > 1 else ''} {names} "
                f"need{'s' if len(reauth) == 1 else ''} to be reconnected before use here."
            )
        for s in persona.mcp_servers:
            if s.transport == "stdio":
                # shlex.split (not str.split) so quoted args survive intact --
                # e.g. a command like
                #   ssh -i ~/.ssh/key user@host "bash -c 'PATH=... npx ...'"
                # needs the quoted bash -c argument kept as ONE arg, not blown
                # apart on every space inside it. A naive .split() would mangle
                # exactly this shape, which is the standard way to reach a
                # remote stdio MCP server (e.g. npx @modelcontextprotocol/
                # server-filesystem) over SSH.
                import shlex

                cmd_parts = shlex.split(s.command or "")
                if cmd_parts:
                    # Built explicitly (not a bare {command, args} dict) so
                    # s.secrets (e.g. GITHUB_PERSONAL_ACCESS_TOKEN, decrypted
                    # by nucleus from MCPServer.secrets_encrypted) can be
                    # passed as subprocess env -- the token never touches the
                    # plain-text `command` string, and stdio servers don't
                    # inherit this process's shell environment by default.
                    client_configs.append(
                        StdioTransport(
                            command=cmd_parts[0],
                            args=cmd_parts[1:],
                            env=s.secrets or None,
                        )
                    )
            else:  # http | sse | streamable-http | websocket
                if s.url:
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
                            # needs_reauth already fails fast above when there's
                            # no valid token -- reaching here with auth_type
                            # oauth2 and no token means the token_env_var
                            # doesn't match what was actually stored. Log and
                            # continue unauthenticated rather than silently
                            # dropping the server.
                            log.warning(
                                "[runner] MCP server %s is oauth2 but has no "
                                "token under '%s' -- connecting without auth.",
                                s.name,
                                s.token_env_var,
                            )
                    if headers is None:
                        # No auth to attach -- pass the bare URL, same as
                        # before, so FastMCPClient's own URL-scheme dispatch
                        # keeps picking the transport (including ws://
                        # websocket servers, which StreamableHttpTransport/
                        # SSETransport don't handle).
                        client_configs.append(s.url)
                    elif s.transport == "sse":
                        client_configs.append(SSETransport(s.url, headers=headers))
                    else:
                        client_configs.append(
                            StreamableHttpTransport(s.url, headers=headers)
                        )

        try:
            async with contextlib.AsyncExitStack() as stack:
                # Open MCP connections and collect available tools
                all_tools: list[dict] = []
                tool_client_map: dict = {}

                for cfg in client_configs:
                    client = await stack.enter_async_context(FastMCPClient(cfg))
                    for t in await client.list_tools():
                        all_tools.append(
                            {
                                "type": "function",
                                "function": {
                                    "name": t.name,
                                    "description": t.description or "",
                                    "parameters": t.inputSchema
                                    or {"type": "object", "properties": {}},
                                },
                            }
                        )
                        tool_client_map[t.name] = client

                # Agentic tool-calling loop (max 10 rounds)
                for _ in range(10):
                    kwargs = _build_litellm_kwargs(model_config, current_messages)
                    kwargs["stream"] = False
                    if all_tools or injected_tools:
                        kwargs["tools"] = all_tools + (injected_tools or [])

                    response = await litellm.acompletion(**kwargs)
                    msg = response.choices[0].message
                    tool_calls = getattr(msg, "tool_calls", None) or []

                    if tool_calls and msg.content:
                        full_response += msg.content
                        yield AgentEvent(
                            type=AgentEventType.DELTA,
                            id=job.msg_id,
                            delta=msg.content + "\n\n",
                        )

                    if not tool_calls:
                        # No more tool calls — stream the final answer
                        final_kwargs = _build_litellm_kwargs(
                            model_config, current_messages
                        )
                        final_response = await litellm.acompletion(**final_kwargs)
                        async for chunk in final_response:
                            delta = chunk.choices[0].delta.content or ""
                            if delta:
                                full_response += delta
                                yield AgentEvent(
                                    type=AgentEventType.DELTA,
                                    id=job.msg_id,
                                    delta=delta,
                                )
                        break

                    # Append assistant message with tool calls
                    current_messages.append(
                        {
                            "role": "assistant",
                            "content": msg.content or "",
                            "tool_calls": [
                                {
                                    "id": tc.id,
                                    "type": "function",
                                    "function": {
                                        "name": tc.function.name,
                                        "arguments": tc.function.arguments,
                                    },
                                }
                                for tc in tool_calls
                            ],
                        }
                    )

                    # Execute each tool via MCP
                    for tc in tool_calls:
                        if injected_tools and any(
                            t["function"]["name"] == tc.function.name
                            for t in injected_tools
                        ):
                            try:
                                args = json.loads(tc.function.arguments or "{}")
                            except json.JSONDecodeError:
                                args = {}

                            yield AgentEvent(
                                type=AgentEventType.TOOL_CALL_START,
                                id=job.msg_id,
                                tool_call=ToolCallData(
                                    name=tc.function.name, args=args
                                ),
                            )
                            # Hand control back to the orchestrator immediately!
                            return

                        # 2. Otherwise, it's a normal MCP tool
                        client = tool_client_map.get(tc.function.name)
                        if client is None:
                            content = f"Tool '{tc.function.name}' not found."
                        else:
                            try:
                                args = json.loads(tc.function.arguments or "{}")
                                result = await client.call_tool(tc.function.name, args)
                                items = (
                                    result
                                    if isinstance(result, list)
                                    else getattr(result, "content", [result])
                                )
                                content = "\n".join(
                                    item.text if hasattr(item, "text") else str(item)
                                    for item in items
                                )
                                is_error = getattr(
                                    result,
                                    "is_error",
                                    getattr(result, "isError", False),
                                )

                                is_error = getattr(
                                    result,
                                    "is_error",
                                    getattr(result, "isError", False),
                                )
                                if is_error:
                                    content = f"Error from tool: {content}"
                            except Exception as exc:
                                content = f"Tool error: {exc}"

                        current_messages.append(
                            {
                                "role": "tool",
                                "content": content,
                                "tool_call_id": tc.id,
                            }
                        )

        except Exception as exc:
            status = "error"
            error_msg = str(exc)
            log.error("[runner] mcp error for job %s: %s", job.job_id, exc)
            raise
        finally:
            latency_ms = int((time.monotonic() - t0) * 1000)
            await _post_ai_request_log(
                job=job,
                persona=persona,
                messages=messages,
                response=full_response,
                prompt_tokens=0,
                completion_tokens=0,
                latency_ms=latency_ms,
                status=status,
                error=error_msg,
            )


def _build_pydantic_model(model_config, settings):
    """
    Map a litellm-convention model_id to the correct pydantic-ai model.

    LiteLLMProvider in pydantic-ai 2.x requires a running LiteLLM proxy server;
    it does NOT do in-process routing. We detect the provider from the model_id
    prefix (e.g. "anthropic/", "openai/") and use native pydantic-ai providers.
    """
    model_id: str = model_config.model_id
    api_key: str | None = model_config.api_key or None

    # Local runtime (Ollama / llama.cpp / LM Studio) — OpenAI-compatible API
    if model_config.provider == "local":
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider

        return OpenAIChatModel(
            model_id,
            provider=OpenAIProvider(
                base_url=f"{settings.OLLAMA_BASE_URL}/v1",
                api_key="local",
            ),
        )

    # Parse litellm prefix: "anthropic/claude-haiku" → ("anthropic", "claude-haiku")
    if "/" in model_id:
        prefix, bare_model = model_id.split("/", 1)
    else:
        prefix, bare_model = "openai", model_id

    if prefix == "anthropic":
        from pydantic_ai.models.anthropic import AnthropicModel
        from pydantic_ai.providers.anthropic import AnthropicProvider

        return AnthropicModel(
            bare_model,
            provider=AnthropicProvider(api_key=api_key)
            if api_key
            else AnthropicProvider(),
        )

    # openai / azure / any OpenAI-compatible provider
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.openai import OpenAIProvider

    return OpenAIChatModel(
        bare_model,
        provider=OpenAIProvider(api_key=api_key) if api_key else OpenAIProvider(),
    )


async def _post_ai_request_log(
    *,
    job: TriggerJob,
    persona: "PersonaConfig",
    messages: list[dict],
    response: str,
    prompt_tokens: int,
    completion_tokens: int,
    latency_ms: int,
    status: str,
    error: str | None,
) -> None:
    """
    Fire-and-forget POST to nucleus internal API to persist the AI request log.

    persona is now passed explicitly (#131) since job only carries persona_id.
    Also fixed here: this call was missing its auth header entirely -- nucleus's
    internal router requires X-Internal-API-Key on every request, so every one
    of these posts was silently getting a 401 and never actually logging
    anything (silently swallowed by the except below, since httpx doesn't
    raise on non-2xx responses unless .raise_for_status() is called).
    """
    url = f"{settings.NEXUS_NUCLEUS_URL}/api/v1/internal/ai-request-logs/"
    payload = {
        "job_id": job.job_id,
        "msg_id": job.msg_id,
        "persona_id": persona.id,
        "model_id": persona.model.model_id,
        "provider": persona.model.provider,
        "prompt": messages,
        "response": response,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "latency_ms": latency_ms,
        "status": status,
        "error": error,
    }
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(
                url,
                json=payload,
                headers={"X-Internal-API-Key": settings.INTERNAL_API_KEY},
            )
    except Exception as exc:
        log.warning("[runner] failed to post AI request log: %s", exc)


def _build_litellm_kwargs(model_config: ModelConfig, messages: list[dict]) -> dict:
    """Build kwargs dict for litellm.acompletion()."""
    kwargs: dict = {
        "model": model_config.model_id,
        "messages": messages,
        "stream": True,
        "max_tokens": model_config.max_tokens,
        "temperature": model_config.temperature,
    }

    if model_config.provider == "local":
        # Local runtime (Ollama, llama.cpp, LM Studio) — OpenAI-compatible API
        kwargs["api_base"] = f"{settings.OLLAMA_BASE_URL}/v1"
        kwargs["api_key"] = "local"
    elif model_config.api_key:
        kwargs["api_key"] = model_config.api_key

    return kwargs
