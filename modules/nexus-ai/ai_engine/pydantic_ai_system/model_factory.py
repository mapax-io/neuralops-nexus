"""
ModelFactory — the only place a ModelSpec becomes a pydantic-ai Model.
Every provider gets its endpoint: base_url is honoured for ALL providers
(0.8.0 applied api_base only to OpenAIProvider — Appendix A defect).
"""
from __future__ import annotations

from pydantic_ai.models import Model
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.providers.google import GoogleProvider
from pydantic_ai.providers.ollama import OllamaProvider
from pydantic_ai.providers.openai import OpenAIProvider

from ai_engine.core.specs import ModelSpec


class UnsupportedProviderError(ValueError):
    pass


class ModelFactory:
    def build(self, spec: ModelSpec) -> Model:
        provider = spec.provider
        if provider in ("openai", "openai_compatible"):
            return OpenAIChatModel(
                spec.model_id,
                provider=OpenAIProvider(api_key=spec.api_key, base_url=spec.base_url),
            )
        if provider == "anthropic":
            kwargs: dict = {"api_key": spec.api_key}
            if spec.base_url:
                kwargs["base_url"] = spec.base_url
            return AnthropicModel(spec.model_id, provider=AnthropicProvider(**kwargs))
        if provider == "google":
            kwargs = {"api_key": spec.api_key}
            if spec.base_url:
                kwargs["base_url"] = spec.base_url
            return GoogleModel(spec.model_id, provider=GoogleProvider(**kwargs))
        if provider == "ollama":
            return OpenAIChatModel(
                spec.model_id,
                provider=OllamaProvider(api_key=spec.api_key or "ollama", base_url=spec.base_url),
            )
        if provider == "deepseek":
            # DeepSeek speaks the OpenAI wire protocol — their own docs call it
            # through the OpenAI client pointed at api.deepseek.com. The default
            # base_url makes the dropdown's deepseek entry work out of the box;
            # an explicit base_url still wins (a proxy, a regional endpoint).
            return OpenAIChatModel(
                spec.model_id,
                provider=OpenAIProvider(api_key=spec.api_key, base_url=spec.base_url or "https://api.deepseek.com/v1"),
            )
        raise UnsupportedProviderError(f"unsupported provider: {provider!r}")
