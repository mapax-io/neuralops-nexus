from apps.interfaces.agent import AgentRunner
from typing import AsyncIterator, Sequence
from pydantic_ai import Agent
from pydantic_ai.models import Model
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.messages import (
    ModelMessage,
    ToolCallPart,
    TextPartDelta,
    TextPart,
    PartDeltaEvent,
    PartStartEvent,
)
from pydantic_ai.capabilities import (
    NativeOrLocalTool,
    WebSearch,
    MCP,
    Thinking,
    ToolSearch,
    WebFetch,
    XSearch,
)
from pydantic_ai_harness import (
    FileSystem,
    Shell,
    Advisor,
    CapabilityCreation,
    SummarizingCompaction,
    DynamicWorkflow,
    LocalStack,
    Memory,
    Planning,
    RepoContext,
    SubAgents,
    SpendLimits,
    Skills,
)
from apps.schemas.trigger import (
    PersonaConfig,
    TriggerJob,
    TriggerSwarmJob,
    AgentEvent,
    AgentEventType,
    NativePydanticAICapabilities,
    ToolCallData,
)

import logging

logger = logging.getLogger(__name__)


class PydanticAIRunner(AgentRunner):
    _MODEL_REGISTRY = {
        "openai": (OpenAIResponsesModel, OpenAIProvider),
        "anthropic": (AnthropicModel, AnthropicProvider),
    }

    _DEFAULT_CAPABILITY_REGISTRY = [
        WebSearch(local="duckduckgo"),
        WebFetch(local=True),
        Shell(
            cwd=".",
            allowed_commands=["ls", "cat", "rg", "touch", "grep", "find", "mkdir"],
            allow_interactive=True,
        ),
        FileSystem(root_dir="."),
        Thinking('medium'),
        Planning(),
    ]

    _OPTIONAL_CAPABILITY_REGISTRY = {
        NativePydanticAICapabilities.ADVISOR: Advisor,
        NativePydanticAICapabilities.CAPABILITY_CREATION: CapabilityCreation,
        NativePydanticAICapabilities.COMPACTION: SummarizingCompaction,
        NativePydanticAICapabilities.DYNAMIC_WORKFLOW: DynamicWorkflow,
        NativePydanticAICapabilities.FILESYSTEM: FileSystem,
        NativePydanticAICapabilities.LOCAL_STACK: LocalStack,
        NativePydanticAICapabilities.MCP: MCP,
        NativePydanticAICapabilities.MEMORY: Memory,
        NativePydanticAICapabilities.PLANNING: Planning,
        NativePydanticAICapabilities.REPO_CONTEXT: RepoContext,
        NativePydanticAICapabilities.SHELL: Shell,
        NativePydanticAICapabilities.SKILLS: Skills,
        NativePydanticAICapabilities.SPEND_LIMITS: SpendLimits,
        NativePydanticAICapabilities.SUBAGENTS: SubAgents,
        NativePydanticAICapabilities.THINKING: Thinking,
        NativePydanticAICapabilities.TOOL_APPROVAL: None,
        NativePydanticAICapabilities.TOOL_SEARCH: ToolSearch,
        NativePydanticAICapabilities.WEB_FETCH: WebFetch,
        NativePydanticAICapabilities.WEB_SEARCH: WebSearch,
        NativePydanticAICapabilities.X_SEARCH: XSearch,
    }

    async def run_stream(
        self,
        job: TriggerJob | TriggerSwarmJob,
        messages: Sequence[ModelMessage],
        persona: PersonaConfig,
        tools: list[dict] | None = None,
    ) -> AsyncIterator[AgentEvent]:
        agent = PydanticAIRunner.build_agent(persona)

        try:
            async with agent.run_stream_events(message_history=messages) as events:
                async for event in events:
                    match event:
                        case PartStartEvent(part=TextPart() as text_part):
                            yield AgentEvent(
                                type=AgentEventType.DELTA,
                                id=job.msg_id,
                                delta=text_part.content,
                            )
                        case PartDeltaEvent(delta=TextPartDelta() as text_delta):
                            # TODO
                            yield AgentEvent(
                                type=AgentEventType.DELTA,
                                id=job.msg_id,
                                delta=text_delta.content_delta,
                            )
                        case PartStartEvent(part=ToolCallPart() as tool_call):
                            yield AgentEvent(
                                type=AgentEventType.TOOL_CALL_START,
                                id=job.msg_id,
                                tool_call=ToolCallData(
                                    name=tool_call.tool_name,
                                    args=tool_call.args_as_dict(),
                                ),
                            )
                        case _:
                            pass

                # All the accrued internal states must persist!
                yield AgentEvent(
                    type=AgentEventType.PERSIST,
                    id=job.msg_id,
                    metadata={"internal_model_state": events.new_messages()}
                )

        except Exception as e:
            logger.error(str(e))
            yield AgentEvent(
                type=AgentEventType.ERROR,
                id=job.msg_id,
                error=str(e),
                error_code="sorry",
            )

    @staticmethod
    def build_agent(persona: PersonaConfig) -> Agent:
        return Agent(
            model=PydanticAIRunner._resolve_model(persona),
            instructions=persona.system_prompt,
            capabilities=PydanticAIRunner._resolve_capabilities(persona.capabilities),
            retries={"tools": 3},
        )

    @classmethod
    def _resolve_capabilities(
        cls, capabilities: list[NativePydanticAICapabilities]
    ) -> list[NativeOrLocalTool]:
        return cls._DEFAULT_CAPABILITY_REGISTRY

    @classmethod
    def _resolve_model(cls, persona: PersonaConfig) -> Model:
        provider_name, model_name = persona.model.provider, persona.model.model_id
        provider_name = provider_name.lower()
        try:
            ModelClass, ProviderClass = PydanticAIRunner._MODEL_REGISTRY[provider_name]
        except KeyError:
            raise
        provider = ProviderClass(api_key=persona.model.api_key)
        return ModelClass(model_name, provider=provider)
