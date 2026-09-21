import asyncio
import logging
import time
from typing import AsyncIterator, Sequence

from pydantic_ai import Agent
from pydantic_ai.capabilities import (
    MCP,
    NativeOrLocalTool,
    Thinking,
    ToolSearch,
    WebFetch,
    WebSearch,
    XSearch,
)
from pydantic_ai.messages import (
    ModelMessage,
    PartDeltaEvent,
    PartStartEvent,
    TextPart,
    TextPartDelta,
    ToolCallPart,
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    ToolReturnPart,
)
from pydantic_ai.models import Model
from pydantic_ai.models.anthropic import AnthropicModel
from fastmcp.client.transports import StdioTransport
from pydantic_ai.models.openai import OpenAIResponsesModel, OpenAIChatModel
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.providers.deepseek import DeepSeekProvider
from pydantic_ai_harness import (
    Advisor,
    CapabilityCreation,
    DynamicWorkflow,
    FileSystem,
    LocalStack,
    Memory,
    Planning,
    RepoContext,
    Shell,
    Skills,
    SpendLimits,
    SubAgents,
    SummarizingCompaction,
    TieredCompaction,
    DeduplicateFileReads,
    ClearToolResults,
)

from apps.core.config import settings
from apps.interfaces.agent import AgentRunner
from apps.implementations.agents.stream_merge import merge_events
from apps.implementations.agents.tool_events import tool_end_event, url_of
from apps.managers.approvals import NucleusApprovals, ToolApprovalGate, nucleus_poll
from apps.managers.fallbacks import MODEL_FAILURE, is_model_failure
from apps.schemas.trigger import (
    ModelConfig,
    AgentEvent,
    AgentEventType,
    PydanticAICapabilities,
    PersonaCapabilities,
    PersonaConfig,
    ToolCallData,
    TriggerJob,
    TriggerSwarmJob,
    MCPArgs,
)

logger = logging.getLogger(__name__)


class PydanticAIRunner(AgentRunner):
    _MODEL_REGISTRY = {
        "openai": (OpenAIResponsesModel, OpenAIProvider),
        "anthropic": (AnthropicModel, AnthropicProvider),
        "deepseek": (OpenAIChatModel, DeepSeekProvider),
        "openai_compatible": (OpenAIChatModel, OpenAIProvider),
    }

    _CAPABILITY_REGISTRY = {
        PydanticAICapabilities.ADVISOR: lambda x: Advisor(**x),
        PydanticAICapabilities.CAPABILITY_CREATION: lambda x: CapabilityCreation(**x),
        PydanticAICapabilities.COMPACTION: lambda x: SummarizingCompaction(**x),
        PydanticAICapabilities.DYNAMIC_WORKFLOW: lambda x: DynamicWorkflow(**x),
        PydanticAICapabilities.FILESYSTEM: lambda x: FileSystem(**x),
        PydanticAICapabilities.LOCAL_STACK: lambda x: LocalStack(**x),
        PydanticAICapabilities.MCP: lambda x: MCP(**x),
        PydanticAICapabilities.MEMORY: lambda x: Memory(**x),
        PydanticAICapabilities.PLANNING: lambda x: Planning(**x),
        PydanticAICapabilities.REPO_CONTEXT: lambda x: RepoContext(**x),
        PydanticAICapabilities.SHELL: lambda x: Shell(**x),
        PydanticAICapabilities.SKILLS: lambda x: Skills(**x),
        PydanticAICapabilities.SPEND_LIMITS: lambda x: SpendLimits(**x),
        PydanticAICapabilities.SUBAGENTS: lambda x: SubAgents(**x),
        PydanticAICapabilities.THINKING: lambda x: Thinking(**x),
        PydanticAICapabilities.TOOL_APPROVAL: None,
        PydanticAICapabilities.TOOL_SEARCH: lambda x: ToolSearch(**x),
        PydanticAICapabilities.WEB_FETCH: lambda x: WebFetch(**x),
        PydanticAICapabilities.WEB_SEARCH: lambda x: WebSearch(**x),
        PydanticAICapabilities.X_SEARCH: lambda x: XSearch(**x),
    }

    async def run_stream(
        self,
        job: TriggerJob | TriggerSwarmJob,
        messages: Sequence[ModelMessage],
        persona: PersonaConfig,
        tools: list[dict] | None = None,
    ) -> AsyncIterator[AgentEvent]:
        # Tool approvals: the gate hides Off tools and holds Ask tools until a
        # person decides; its requests and the keepalives ride the same stream
        # as the model's own events (stream_merge).
        side: asyncio.Queue = asyncio.Queue()
        gate = ToolApprovalGate(
            levels=persona.tool_levels,
            ask=NucleusApprovals(job.msg_id, poll=nucleus_poll(job.msg_id), emit=side.put_nowait),
            # A swarm job carries no flag: nobody stores its requests, so it
            # refuses Ask tools at once rather than waiting on a poll.
            interactive=getattr(job, "interactive", False),
        )
        agent = PydanticAIRunner.build_agent(persona, gate)

        buffer: list[str] = []
        previous_flush_time = time.monotonic()
        flush_granularity: float = 0.05
        # When each tool call began, by call id, so its end event can say how long it took.
        tool_started_at: dict[str, float] = {}
        # The call's arguments, so the end event can say where a web tool went.
        tool_args: dict[str, tuple[str, dict]] = {}
        usage: dict | None = None

        try:
            async with agent.run_stream_events(message_history=messages) as events:
                async for event in merge_events(events, side, keepalive_seconds=settings.STREAM_KEEPALIVE_SECONDS, msg_id=job.msg_id):
                    if isinstance(event, AgentEvent):
                        yield event  # an approval request or a keepalive, ready as it is
                        continue
                    match event:
                        case PartStartEvent(part=TextPart() as text_part):
                            buffer.append(text_part.content)
                        case PartDeltaEvent(delta=TextPartDelta() as text_delta):
                            buffer.append(text_delta.content_delta)
                            now = time.monotonic()

                            # Flush the buffer if it has been [flush_granularity] seconds since the last flush
                            if now - previous_flush_time >= flush_granularity:
                                chunk = "".join(buffer)
                                buffer.clear()
                                previous_flush_time = now
                                yield AgentEvent(
                                    type=AgentEventType.DELTA,
                                    id=job.msg_id,
                                    delta=chunk,
                                )

                        case PartStartEvent(part=ToolCallPart() as tool_call):
                            # Flush the buffer before tending to the tool call
                            if len(buffer) > 0:
                                chunk = "".join(buffer)
                                buffer.clear()
                                previous_flush_time = time.monotonic()
                                yield AgentEvent(
                                    type=AgentEventType.DELTA,
                                    id=job.msg_id,
                                    delta=chunk
                                )

                        case FunctionToolCallEvent(part=tool_call):
                            # Fired when the call actually runs, with its
                            # arguments complete -- the part-start above only
                            # knows the name while the arguments still stream.
                            tool_started_at[tool_call.tool_call_id] = time.monotonic()
                            tool_args[tool_call.tool_call_id] = (tool_call.tool_name, tool_call.args_as_dict())
                            yield AgentEvent(
                                type=AgentEventType.TOOL_CALL_START,
                                id=job.msg_id,
                                tool_call=ToolCallData(
                                    name=tool_call.tool_name,
                                    args=tool_call.args_as_dict(),
                                ),
                            )
                        case FunctionToolResultEvent(part=result_part):
                            # A ToolReturnPart is a result; a RetryPromptPart is
                            # the tool refusing or failing, sent back to the model.
                            ok = isinstance(result_part, ToolReturnPart)
                            yield tool_end_event(
                                job.msg_id,
                                result_part.tool_name or "",
                                ok=ok,
                                # A call that waited for a person is timed from the decision, not the request.
                                started_at=tool_started_at.pop(result_part.tool_call_id, time.monotonic()) + gate.waits.pop(result_part.tool_call_id, 0.0),
                                content=result_part.content if ok else None,
                                error=None if ok else str(result_part.content),
                                url=url_of(*tool_args.pop(result_part.tool_call_id, (result_part.tool_name or "", {}))),
                            )
                        case _:
                            pass

                # Flush buffer text before wrapping up
                if len(buffer)>0:
                    chunk = "".join(buffer)
                    buffer.clear()
                    yield AgentEvent(
                        type=AgentEventType.DELTA,
                        id=job.msg_id,
                        delta=chunk,
                    )
                # What the run cost -- `usage` is a property on the stream --
                # so the manager can put it on message_done.
                run_usage = getattr(events, "usage", None)
                usage = (
                    {"prompt_tokens": run_usage.input_tokens, "output_tokens": run_usage.output_tokens}
                    if run_usage is not None and not callable(run_usage)
                    else None
                )
                # All the accrued internal states must persist!
                yield AgentEvent(
                    type=AgentEventType.PERSIST,
                    id=job.msg_id,
                    metadata={"internal_model_state": events.new_messages(), "usage": usage}
                )

        except Exception as e:
            logger.error(str(e))
            yield AgentEvent(
                type=AgentEventType.ERROR,
                id=job.msg_id,
                error=str(e),
                # A model that could not be used lets the fallback run try the next one.
                error_code=MODEL_FAILURE if is_model_failure(e) else "sorry",
            )

    @staticmethod
    def build_agent(persona: PersonaConfig, gate: ToolApprovalGate | None = None) -> Agent:
        capabilities = PydanticAIRunner._resolve_capabilities(persona.capabilities, persona.mcp_servers, persona.model.max_tokens)
        return Agent(
            model=PydanticAIRunner._resolve_model(persona),
            instructions=persona.system_prompt,
            capabilities=capabilities + ([gate] if gate is not None else []),
            retries={
                "tools": 3,
                "output": 3,
            }
        )

    @classmethod
    def _resolve_capabilities(
        cls, capabilities: PersonaCapabilities, mcp_servers: list[MCPArgs], max_tokens: int
    ) -> list[NativeOrLocalTool]:

        token_target = max(max_tokens - 20_000, int(0.9 * max_tokens))

        resolved = []

        resolved.append(ToolSearch(strategy=None))

        resolved.append(
            TieredCompaction(
                tiers=[
                    DeduplicateFileReads(file_key=cls._file_key_extractor),
                    ClearToolResults(max_fraction=0.9, keep_pairs=5),
                    SummarizingCompaction(receipts=True,
                                          keep_user_messages=True,
                                          max_tokens=token_target)],
                target_tokens=token_target,
            )
        )

        # Explicit ids: every tool definition then names its source
        # (ToolDefinition.capability_id), which is what a tool level is keyed by.
        if capabilities.filesystem is not None:
            resolved.append(FileSystem(id="filesystem", **capabilities.filesystem.model_dump(exclude_none=True)))
        if capabilities.web_search is not None:
            resolved.append(WebSearch(**capabilities.web_search.model_dump(exclude_none=True)))
        if capabilities.shell is not None:
            resolved.append(Shell(id="shell", **capabilities.shell.model_dump(exclude_none=True)))

        for mcp_server in mcp_servers:
            mcp_id = {"id": f"mcp:{mcp_server.id}"} if mcp_server.id else {}
            if mcp_server.url:
                mcp_kwargs = {"url": mcp_server.url, **mcp_id}
                if mcp_server.authorization_token:
                    mcp_kwargs["headers"] = {
                        "Authorization": f"Bearer {mcp_server.authorization_token}"
                    }
                resolved.append(MCP(**mcp_kwargs))
                
            elif mcp_server.command:
                transport = StdioTransport(
                    command=mcp_server.command,
                    args=mcp_server.args,
                    env=mcp_server.env if mcp_server.env else None
                )
                resolved.append(MCP(local=transport, defer_loading=True, **mcp_id))

        return resolved



    @classmethod
    def _resolve_model(cls, persona: PersonaConfig) -> Model:
        return PydanticAIRunner.build_model(persona.model)

    @staticmethod
    def build_model(config: ModelConfig) -> Model:
        """The pydantic-ai model for one config -- what a persona runs on, and what a model check dials."""
        provider_name, model_name = config.provider.lower(), config.model_id
        try:
            ModelClass, ProviderClass = PydanticAIRunner._MODEL_REGISTRY[provider_name]
        except KeyError:
            raise
        # An api_base (a compatible endpoint, a proxy) only means something to the OpenAI-shaped providers.
        kwargs = {"base_url": config.api_base} if config.api_base and ProviderClass is OpenAIProvider else {}
        provider = ProviderClass(api_key=config.api_key, **kwargs)
        return ModelClass(model_name, provider=provider)
    
    @staticmethod
    def _file_key_extractor(call: ToolCallPart) -> str | None:
        if call.tool_name == 'read_file':
            try:
                return call.args_as_dict().get('path')
            except Exception:
                return None
        return None
