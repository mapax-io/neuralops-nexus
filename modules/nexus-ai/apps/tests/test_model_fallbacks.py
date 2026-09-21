"""
W7 Model fallbacks: when the persona's model cannot answer, the turn is
retried on the next model of its ordered fallback list -- before anything
reached the reader -- and the reply says which model answered.
"""
import pytest

from apps.managers.fallbacks import MODEL_FAILURE, FallbackRun, is_model_failure
from apps.managers.nucleus_client import model_from, persona_from
from apps.schemas.trigger import AgentEvent, AgentEventType, ModelConfig, PersonaCapabilities, PersonaConfig, TriggerJob


def model(name, **over) -> ModelConfig:
    base = dict(provider="openai", model_id=name.lower(), api_key="k", name=name)
    base.update(over)
    return ModelConfig(**base)


def persona(*fallbacks) -> PersonaConfig:
    return PersonaConfig(id="pe1", name="Sara", system_prompt="You are Sara.", model=model("Primary"),
                         mcp_servers=[], capabilities=PersonaCapabilities(), fallback_models=list(fallbacks))


def job() -> TriggerJob:
    return TriggerJob(job_id="j", msg_id="m", persona_id="p", topic_id="t", user_message_id="u", message="x")


class Failing(Exception):
    def __init__(self, status_code=None, text="boom"):
        super().__init__(text)
        if status_code is not None:
            self.status_code = status_code


# ── what counts as the model failing ─────────────────────────────────────────
def test_status_codes_decide_first():
    for status in (401, 402, 403, 404, 408, 429, 500, 502, 503, 529):
        assert is_model_failure(Failing(status)), status
    for status in (400, 422):
        assert not is_model_failure(Failing(status, "context_length_exceeded")), status
    # An empty balance reported as a 400 (Anthropic) is the model being unusable, not the request being wrong.
    assert is_model_failure(Failing(400, "invalid_request_error: Your credit balance is too low to access the Anthropic API."))


def test_known_classes_and_text_decide_when_there_is_no_status():
    RateLimitError = type("RateLimitError", (Exception,), {})
    ContentPolicyViolationError = type("ContentPolicyViolationError", (Exception,), {})
    assert is_model_failure(RateLimitError("slow down"))
    assert not is_model_failure(ContentPolicyViolationError("nope"))
    assert is_model_failure(RuntimeError("Error code: 429 - rate limit reached"))
    assert is_model_failure(RuntimeError("connection error: peer closed connection"))
    assert is_model_failure(RuntimeError("httpx.ConnectError: connection refused"))  # not the model refusing
    assert not is_model_failure(RuntimeError("This model's maximum context length is 8192 tokens"))
    assert not is_model_failure(RuntimeError("the model refused: content filter"))
    assert not is_model_failure(RuntimeError("something odd"))


# ── the run ──────────────────────────────────────────────────────────────────
class Runner:
    """Scripted attempts: each entry is the event list one attempt yields; records which model each attempt ran on."""

    def __init__(self, *attempts):
        self.attempts = list(attempts)
        self.models: list[str] = []

    async def run_stream(self, job, messages, persona, tools=None):
        self.models.append(persona.model.name)
        for event in self.attempts.pop(0):
            yield event


def error(code=MODEL_FAILURE, text="Error code: 429"):
    return AgentEvent(type=AgentEventType.ERROR, id="m", error=text, error_code=code)


def delta(text):
    return AgentEvent(type=AgentEventType.DELTA, id="m", delta=text)


async def collect(run):
    return [e async for e in run.events()]


@pytest.mark.asyncio
async def test_a_failed_model_hands_the_turn_to_the_next_one_and_the_reply_says_so():
    runner = Runner([error()], [error(text="Error code: 401")], [delta("hi"), delta("!")])
    run = FallbackRun(runner, job(), [], persona(model("Small"), model("Tiny")))
    events = await collect(run)
    assert [e.delta for e in events] == ["hi", "!"]  # the failures never reach the reader
    assert runner.models == ["Primary", "Small", "Tiny"]
    assert run.answered_by_model == "Tiny (fallback)" and run.model.name == "Tiny"


@pytest.mark.asyncio
async def test_a_reply_from_the_primary_carries_no_label():
    runner = Runner([delta("hi")])
    run = FallbackRun(runner, job(), [], persona(model("Small")))
    await collect(run)
    assert run.answered_by_model is None and runner.models == ["Primary"]


@pytest.mark.asyncio
async def test_a_failure_after_text_reached_the_reader_is_reported_not_retried():
    runner = Runner([delta("half"), error()], [delta("never")])
    run = FallbackRun(runner, job(), [], persona(model("Small")))
    events = await collect(run)
    assert [e.type for e in events] == [AgentEventType.DELTA, AgentEventType.ERROR]
    assert runner.models == ["Primary"] and run.answered_by_model is None


@pytest.mark.asyncio
async def test_other_errors_and_an_exhausted_list_pass_the_error_through():
    runner = Runner([error(code="sorry", text="NameError: x")], [delta("never")])
    events = await collect(FallbackRun(runner, job(), [], persona(model("Small"))))
    assert [e.type for e in events] == [AgentEventType.ERROR] and runner.models == ["Primary"]

    runner = Runner([error()], [error(text="Error code: 503")])
    run = FallbackRun(runner, job(), [], persona(model("Small")))
    events = await collect(run)
    assert [e.type for e in events] == [AgentEventType.ERROR] and events[0].error == "Error code: 503"
    assert runner.models == ["Primary", "Small"]


@pytest.mark.asyncio
async def test_a_persona_without_fallbacks_runs_once():
    runner = Runner([error()], [delta("never")])
    events = await collect(FallbackRun(runner, job(), [], persona()))
    assert [e.type for e in events] == [AgentEventType.ERROR] and runner.models == ["Primary"]


@pytest.mark.asyncio
async def test_the_manager_puts_the_answering_model_on_message_done(monkeypatch):
    from apps.managers import agentic_manager
    from apps.managers.agentic_manager import NewImprovedAgenticManager

    async def fake_persona(_): return persona(model("Small"))
    async def fake_history(**_): return []
    async def fake_resolve(_, __=()): return "text", None
    monkeypatch.setattr(agentic_manager.nucleus_client, "resolve_persona", fake_persona)
    monkeypatch.setattr(agentic_manager.nucleus_client, "fetch_history", fake_history)
    monkeypatch.setattr(agentic_manager, "resolve_output_spec", fake_resolve)
    monkeypatch.setattr(agentic_manager, "context_window_for", lambda m: {"primary": 8_000, "small": 128_000}[m.model_id])
    manager = NewImprovedAgenticManager(runner=Runner([error()], [delta("Hello")]), embedder=None, store=None)
    events = [e async for e in manager.run(job())]
    done = next(e for e in events if e.type == AgentEventType.END)
    assert (done.content, done.answered_by_model, done.context_window) == ("Hello", "Small (fallback)", 128_000)
    assert not any(e.type == AgentEventType.ERROR for e in events)


# ── nucleus's payload ────────────────────────────────────────────────────────
def test_the_payload_s_fallbacks_and_model_names_are_read():
    data = {"id": "pe1", "name": "Sara", "prompt": {"system_prompt": "hi"}, "capabilities": [], "mcp_servers": [],
            "model": {"id": "m1", "name": "Big", "provider": "openai", "model_id": "gpt-4o", "api_key": "k1"},
            "fallback_models": [{"id": "m2", "name": "Small", "provider": "openai", "model_id": "gpt-4o-mini", "api_key": "k2"},
                                {"id": "m3", "name": "Tiny", "provider": "anthropic", "model_id": "claude-haiku-4-5-20251001", "api_key": "k3"}]}
    p = persona_from(data)
    assert p.model.name == "Big"
    assert [(m.name, m.model_id, m.api_key) for m in p.fallback_models] == [("Small", "gpt-4o-mini", "k2"), ("Tiny", "claude-haiku-4-5-20251001", "k3")]
    assert persona_from({**data, "fallback_models": None}).fallback_models == []  # an older nucleus sends none
    assert model_from(None).name is None
