"""
LLMFactory — returns the right LLMModel implementation based on config.
Add a new provider: implement LLMModel, register it here.
"""
from apps.interfaces.llm import LLMModel
from apps.core.config import settings


class LLMFactory:
    @staticmethod
    def get(provider: str | None = None, model_id: str | None = None) -> LLMModel:
        provider = provider or settings.LLM_PROVIDER

        match provider:
            case "litellm":
                from apps.implementations.llm.litellm_model import LiteLLMModel
                return LiteLLMModel(model_id=model_id)

            case "openai":
                from apps.implementations.llm.litellm_model import LiteLLMModel
                return LiteLLMModel(model_id=f"openai/{model_id}")

            case "anthropic":
                from apps.implementations.llm.litellm_model import LiteLLMModel
                return LiteLLMModel(model_id=f"anthropic/{model_id}")

            case "ollama":
                from apps.implementations.llm.litellm_model import LiteLLMModel
                return LiteLLMModel(model_id=f"ollama/{model_id}")

            case _:
                raise ValueError(f"Unknown LLM provider: {provider!r}")
