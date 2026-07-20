"""
AgentFactory — returns the right AgentRunner based on config.
Switch from Pydantic AI to LangGraph: implement AgentRunner, register here.
"""
from apps.interfaces.agent import AgentRunner
from apps.core.config import settings


class AgentFactory:
    @staticmethod
    def get(backend: str | None = None) -> AgentRunner:
        backend = backend or settings.AGENT_BACKEND

        match backend:
            case "pydantic_ai":
                from apps.implementations.agents.pydantic_ai_runner import PydanticAIRunner
                return PydanticAIRunner()

            case "langgraph":
                from apps.implementations.agents.langgraph_runner import LangGraphRunner
                return LangGraphRunner()

            case "agno":
                from apps.implementations.agents.agno_runner import AgnoRunner
                return AgnoRunner()

            case _:
                raise ValueError(f"Unknown agent backend: {backend!r}")
