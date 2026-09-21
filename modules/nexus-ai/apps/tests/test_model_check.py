"""
Model check: a tiny call with the given key before a model is saved -- built
the way a persona run builds it, answered as a category nucleus can word.
"""
import asyncio

import pytest
from fastapi.testclient import TestClient

from apps.core.config import settings
from apps.managers import model_check
from apps.managers.model_check import check_model
from apps.schemas.trigger import ModelConfig


def config(**over) -> ModelConfig:
    base = dict(provider="openai", model_id="gpt-4o-mini", api_key="sk-test")
    base.update(over)
    return ModelConfig(**base)


class FakeAgent:
    """Stands in for pydantic_ai.Agent: `outcome` is what run() does."""
    outcome = None

    def __init__(self, model=None, **_):
        self.model = model

    async def run(self, prompt, model_settings=None):
        assert model_settings == {"max_tokens": 5}
        if isinstance(FakeAgent.outcome, BaseException):
            raise FakeAgent.outcome
        if FakeAgent.outcome == "hang":
            await asyncio.sleep(5)
        return "OK"


@pytest.fixture(autouse=True)
def fake_agent(monkeypatch):
    FakeAgent.outcome = None
    monkeypatch.setattr(model_check, "Agent", FakeAgent)


class Failing(Exception):
    def __init__(self, status_code, text):
        super().__init__(text)
        self.status_code = status_code


@pytest.mark.asyncio
async def test_a_model_that_answers_passes_with_its_latency():
    out = await check_model(config())
    assert out["ok"] is True and isinstance(out["latency_ms"], int)


@pytest.mark.asyncio
async def test_a_model_that_cannot_be_used_says_so_with_the_status():
    FakeAgent.outcome = Failing(401, "Error code: 401 - Incorrect API key provided")
    out = await check_model(config())
    assert (out["ok"], out["error_code"], out["status_code"]) == (False, "model_failure", 401)
    assert "Incorrect API key" in out["error"]
    FakeAgent.outcome = Failing(400, "maximum context length exceeded")
    assert (await check_model(config()))["error_code"] == "error"  # the model answering, not failing


@pytest.mark.asyncio
async def test_a_provider_this_worker_cannot_run_is_refused_before_any_call():
    out = await check_model(config(provider="google"))
    assert out == {"ok": False, "error_code": "unsupported_provider", "error": "provider 'google' is not supported by this worker"}


@pytest.mark.asyncio
async def test_a_model_that_never_answers_times_out():
    FakeAgent.outcome = "hang"
    out = await check_model(config(), timeout=0.05)
    assert out["ok"] is False and out["error_code"] == "timeout" and "timed out" in out["error"]


def test_the_model_is_built_like_a_persona_run_including_the_api_base():
    from apps.implementations.agents.pydantic_ai_runner import PydanticAIRunner
    model = PydanticAIRunner.build_model(config(provider="openai_compatible", api_base="https://llm.example.test/v1"))
    assert model.model_name == "gpt-4o-mini"
    assert model._provider.base_url.rstrip("/") == "https://llm.example.test/v1"
    plain = PydanticAIRunner.build_model(config())
    assert "api.openai.com" in plain._provider.base_url


def test_the_route_needs_the_internal_key_and_answers_the_check():
    from apps.main import app
    client = TestClient(app)
    body = {"provider": "openai", "model_id": "gpt-4o-mini", "api_key": "sk-test"}
    assert client.post("/api/v1/models/check/", json=body).status_code == 401
    r = client.post("/api/v1/models/check/", json=body, headers={"X-Internal-Key": settings.INTERNAL_API_KEY})
    assert r.status_code == 200 and r.json()["ok"] is True
