"""
LLMFactory — returns the right LLMModel implementation based on config.

Two providers:
  litellm  — routes to any cloud/hosted provider via LiteLLM.
             model_id encodes the provider: "anthropic/claude-haiku-4-5-20251001",
             "openai/gpt-4o", "ollama/llama3", "azure/gpt-4", etc.
  local    — reserved for future direct ONNX/llama.cpp runtimes inside nexus-ai
             that bypass LiteLLM entirely.

Swap provider via LLM_PROVIDER env var — zero code changes.
Add a new provider: implement LLMModel interface, register it here.
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

            case "local":
                # Placeholder for future direct ONNX/llama.cpp runtimes.
                raise NotImplementedError("Local LLM provider not yet implemented.")

            case _:
                raise ValueError(
                    f"Unknown LLM provider: {provider!r}. "
                    f"Valid options: 'litellm', 'local'"
                )
