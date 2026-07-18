"""
Pydantic AI implementation of AgentRunner — Phase 1.
Swap for LangGraphRunner by changing AGENT_BACKEND env var.
"""
from __future__ import annotations

from typing import AsyncIterator

from pydantic_ai import Agent
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.openai import OpenAIModel

from apps.interfaces.agent import AgentRunner
from apps.schemas.trigger import TriggerJob, AgentEvent
from apps.core.config import settings


def _get_pydantic_ai_model(persona_model):
    """Build the correct Pydantic AI model from persona config."""
    provider = persona_model.provider
    model_id = persona_model.model_id

    match provider:
        case "anthropic":
            return AnthropicModel(model_id)
        case "openai":
            return OpenAIModel(model_id)
        case "ollama":
            # Ollama exposes an OpenAI-compatible API — use the docker service URL
            return OpenAIModel(
                model_id,
                base_url=f"{settings.OLLAMA_BASE_URL}/v1",
                api_key="ollama",
            )
        case _:
            # Fallback: treat model_id as a fully-qualified litellm string
            # and use Anthropic as the wire format (most common)
            return AnthropicModel(model_id)


class PydanticAIRunner(AgentRunner):
    """
    Runs the agent using Pydantic AI.
    Receives the fully-assembled messages list from PromptBuilder and
    yields message_delta events.
    """

    async def run_stream(
        self,
        job: TriggerJob,
        messages: list[dict],
    ) -> AsyncIterator[AgentEvent]:
        model = _get_pydantic_ai_model(job.persona.model)

        agent = Agent(
            model=model,
            system_prompt=job.persona.system_prompt,
        )

        # Convert to pydantic-ai history format (excludes system + last user msg)
        history = _to_pydantic_history(messages)

        async with agent.run_stream(job.message, message_history=history) as result:
            async for token in result.stream_text(delta=True):
                yield AgentEvent(
                    type="message_delta",
                    id=job.msg_id,
                    delta=token,
                )


def _to_pydantic_history(messages: list[dict]) -> list:
    """
    Convert our OpenAI-format messages to Pydantic AI's ModelMessage format.
    Skips the system message (handled by Agent) and the last user message
    (that becomes the prompt passed to run_stream).
    """
    from pydantic_ai.messages import ModelRequest, ModelResponse, UserPromptPart, TextPart

    history = []
    # Skip system messages; skip the final user message (it's the prompt)
    relevant = [m for m in messages if m["role"] != "system"][:-1]

    for msg in relevant:
        if msg["role"] == "user":
            history.append(ModelRequest(parts=[UserPromptPart(content=msg["content"])]))
        elif msg["role"] == "assistant":
            history.append(ModelResponse(parts=[TextPart(content=msg["content"])]))

    return history
