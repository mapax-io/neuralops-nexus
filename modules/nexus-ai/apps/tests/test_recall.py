"""
W5 Recall: the project's recorded decisions/facts/preferences are embedded
per entry, retrieved by project into their own prompt block, and proposed
by the utility model after a reply.
"""
import asyncio

import pytest
from fastapi.testclient import TestClient

from apps.core.config import settings
from apps.implementations.context_sources.recall.recall_context_source import RECALL_LABEL, RecallContextSource
from apps.interfaces.vectorstore import Chunk
from apps.managers import recall as recall_module
from apps.managers.recall import RememberEntry, RememberOutput, project_id_of, remember
from apps.managers.nucleus_client import persona_from
from apps.schemas.embed import RecallEmbedRequest
from apps.schemas.trigger import AgentEvent, AgentEventType, ContextSourceRef, ModelConfig, PersonaCapabilities, PersonaConfig, TriggerJob


class FakeEmbedder:
    async def embed(self, texts):
        return [[float(len(t)), 1.0] for t in texts]

    async def embed_query(self, text):
        return [float(len(text)), 1.0]


class FakeStore:
    def __init__(self):
        self.docs: dict[tuple[str, str], tuple[str, dict]] = {}
        self.searches = []

    async def store(self, texts, vectors, metadatas, collection_id, ids=None):
        for text, meta, doc_id in zip(texts, metadatas, ids):
            self.docs[(collection_id, doc_id)] = (text, meta)

    async def search(self, query_vector, collection_id, top_k=5, filter=None):
        self.searches.append((collection_id, top_k, filter))
        return [Chunk(text=t, score=0.9, metadata=m) for (c, _), (t, m) in self.docs.items()
                if c == collection_id and (not filter or all(m.get(k) == v for k, v in filter.items()))]

    async def delete_collection(self, collection_id):
        self.docs = {k: v for k, v in self.docs.items() if k[0] != collection_id}

    async def delete_by_ids(self, collection_id, ids):
        for doc_id in ids:
            self.docs.pop((collection_id, doc_id), None)


def persona(**over) -> PersonaConfig:
    base = dict(id="pe1", name="Sara", system_prompt="You are Sara.", model=ModelConfig(provider="openai", model_id="gpt-4o", api_key="k"),
                mcp_servers=[], capabilities=PersonaCapabilities())
    base.update(over)
    return PersonaConfig(**base)


def job(**over) -> TriggerJob:
    base = dict(job_id="j", msg_id="m", persona_id="pe1", topic_id="t", user_message_id="u", message="Let's use Postgres.",
                context_sources=[ContextSourceRef(source_id="t", type="chat", label="Chat History", collection_id="company_c_chat"),
                                 ContextSourceRef(source_id="p1", type="recall", label="Recall", collection_id="company_c_recall")])
    base.update(over)
    return TriggerJob(**base)


# ── the plugin ───────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_an_entry_is_embedded_by_id_retrieved_by_project_and_removed_by_id():
    store = FakeStore()
    source = RecallContextSource(embedder=FakeEmbedder(), store=store)
    req = RecallEmbedRequest(entry_id="e1", company_id="c", project_id="p1", kind="decision", text="We use Postgres.", author_name="Sara", topic_id="t1", created_at="2026-09-21T00:00:00Z")
    out = await source.ingest(req)
    assert (out.ok, out.collection) == (True, "company_c_recall")
    await source.ingest(RecallEmbedRequest(entry_id="e2", company_id="c", project_id="p2", kind="fact", text="Other project."))
    chunks = await source.retrieve("database", "company_c_recall", top_k=8, filter={"source_id": "p1"})  # what the prompt builder passes
    assert [c.text for c in chunks] == ["We use Postgres."]
    assert chunks[0].metadata["label"] == RECALL_LABEL and chunks[0].metadata["type"] == "recall" and chunks[0].metadata["kind"] == "decision"
    assert store.searches[-1] == ("company_c_recall", 8, {"project_id": "p1"})
    # An edit re-embeds under the same id: one doc, new text.
    await source.ingest(RecallEmbedRequest(entry_id="e1", company_id="c", project_id="p1", kind="decision", text="We use Postgres 16."))
    assert [c.text for c in await source.retrieve("database", "company_c_recall", filter={"project_id": "p1"})] == ["We use Postgres 16."]
    await source.delete_entry("e1", "c")
    assert await source.retrieve("database", "company_c_recall", filter={"project_id": "p1"}) == []


def test_the_embed_routes_need_the_key_and_reach_the_plugin(monkeypatch):
    from apps.main import app
    from apps.factories import context_source as factory
    store = FakeStore()
    monkeypatch.setattr(factory.EmbeddingFactory, "get", staticmethod(lambda: FakeEmbedder()))
    monkeypatch.setattr(factory.VectorStoreFactory, "get", staticmethod(lambda: store))
    client = TestClient(app)
    body = {"entry_id": "e1", "company_id": "c", "project_id": "p1", "kind": "fact", "text": "Standup at ten."}
    assert client.post("/api/v1/embed/recall/", json=body).status_code == 401
    r = client.post("/api/v1/embed/recall/", json=body, headers={"X-Internal-Key": settings.INTERNAL_API_KEY})
    assert r.status_code == 200 and r.json()["ok"] is True
    assert ("company_c_recall", "e1") in store.docs
    r = client.delete("/api/v1/embed/recall/e1/", params={"company_id": "c"}, headers={"X-Internal-Key": settings.INTERNAL_API_KEY})
    assert r.status_code == 200 and ("company_c_recall", "e1") not in store.docs


# ── the prompt block ─────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_recall_gets_its_own_block_after_the_attached_context(monkeypatch):
    from apps.managers import prompt_builder
    from apps.managers.prompt_builder import NewImprovedPromptBuilder

    class Plugin:
        def __init__(self, chunks):
            self.chunks = chunks
            self.calls = []

        async def retrieve(self, query, collection_id, top_k=5, filter=None):
            self.calls.append((collection_id, top_k, filter))
            return self.chunks

    plugins = {
        "chat": Plugin([Chunk(text="earlier: we picked blue", score=0.8, metadata={"label": "Chat History"})]),
        "recall": Plugin([Chunk(text="We use Postgres.", score=0.9, metadata={"type": "recall", "label": RECALL_LABEL, "kind": "decision", "author_name": "Sara"})]),
    }
    monkeypatch.setattr(prompt_builder.ContextSourceFactory, "get", staticmethod(lambda directive: plugins[directive]))
    messages = await NewImprovedPromptBuilder().build(job=job(), persona=persona(), history=[])
    texts = [part.content for m in messages for part in m.parts if hasattr(part, "content")]
    context_block = next(t for t in texts if t.startswith("[Relevant context"))
    recall_block = next(t for t in texts if t.startswith(f"[{RECALL_LABEL}]"))
    assert "earlier: we picked blue" in context_block and "We use Postgres." not in context_block
    assert "- (decision, Sara) We use Postgres." in recall_block
    assert texts.index(recall_block) > texts.index(context_block)
    assert plugins["recall"].calls == [("company_c_recall", settings.RECALL_TOP_K, {"source_id": "p1"})]
    # No recall source (the persona has recall off): no block, no call.
    plugins["recall"].calls.clear()
    messages = await NewImprovedPromptBuilder().build(job=job(context_sources=[job().context_sources[0]]), persona=persona(), history=[])
    assert not any(part.content.startswith(f"[{RECALL_LABEL}]") for m in messages for part in m.parts if hasattr(part, "content"))
    assert plugins["recall"].calls == []


# ── the remember pass ────────────────────────────────────────────────────────
class FakeAgent:
    output = RememberOutput()
    seen = {}

    def __init__(self, model=None, instructions=None, output_type=None, **_):
        FakeAgent.seen = {"model": model, "output_type": output_type}

    async def run(self, prompt, model_settings=None):
        FakeAgent.seen["prompt"] = prompt
        if FakeAgent.output == "hang":
            await asyncio.sleep(5)

        class Result:
            output = FakeAgent.output
        return Result()


@pytest.fixture
def fake_agent(monkeypatch):
    FakeAgent.output = RememberOutput()
    monkeypatch.setattr(recall_module, "Agent", FakeAgent)
    monkeypatch.setattr("apps.implementations.agents.pydantic_ai_runner.PydanticAIRunner.build_model", staticmethod(lambda config: f"model:{config.model_id}"))
    posted = []

    async def fake_record(project_id, persona_id, message_id, entries):
        posted.append((project_id, persona_id, message_id, entries))
        return len(entries)
    monkeypatch.setattr(recall_module.nucleus_client, "record_recall", fake_record)
    return posted


@pytest.mark.asyncio
async def test_the_pass_runs_on_the_utility_model_and_records_valid_entries(fake_agent):
    FakeAgent.output = RememberOutput(entries=[
        RememberEntry(kind="Decision", text="  We use  Postgres. "), RememberEntry(kind="wish", text="nope"), RememberEntry(kind="fact", text=""),
        RememberEntry(kind="preference", text="Answer in bullet points."),
    ])
    small = ModelConfig(provider="openai", model_id="gpt-4o-mini", api_key="k2")
    n = await remember(job(), persona(utility_model=small), "Sure — Postgres it is.")
    assert n == 2
    assert fake_agent == [("p1", "pe1", "m", [{"kind": "decision", "text": "We use Postgres."}, {"kind": "preference", "text": "Answer in bullet points."}])]
    assert FakeAgent.seen["model"] == "model:gpt-4o-mini" and FakeAgent.seen["output_type"] is RememberOutput
    assert "Let's use Postgres." in FakeAgent.seen["prompt"] and "Reply from Sara" in FakeAgent.seen["prompt"]


@pytest.mark.asyncio
async def test_nothing_is_recorded_without_recall_or_a_reply_or_when_the_model_proposes_nothing(fake_agent):
    FakeAgent.output = RememberOutput(entries=[RememberEntry(kind="fact", text="x")])
    assert await remember(job(context_sources=[job().context_sources[0]]), persona(), "hi") == 0  # nucleus sent no recall source
    assert await remember(job(), persona(recall_enabled=False), "hi") == 0
    assert await remember(job(), persona(), "   ") == 0
    FakeAgent.output = RememberOutput()
    assert await remember(job(), persona(), "hi") == 0
    assert fake_agent == []


@pytest.mark.asyncio
async def test_a_failing_or_slow_pass_never_touches_the_reply(fake_agent, monkeypatch):
    FakeAgent.output = "hang"
    monkeypatch.setattr(settings, "RECALL_REMEMBER_TIMEOUT_SECONDS", 0.05)
    assert await remember(job(), persona(), "hi") == 0
    FakeAgent.output = RememberOutput(entries=[RememberEntry(kind="fact", text="x")])

    async def failing(*_):
        raise RuntimeError("nucleus away")
    monkeypatch.setattr(recall_module.nucleus_client, "record_recall", failing)
    assert await remember(job(), persona(), "hi") == 0


@pytest.mark.asyncio
async def test_the_manager_puts_what_was_recorded_on_message_done(monkeypatch):
    from apps.managers import agentic_manager
    from apps.managers.agentic_manager import NewImprovedAgenticManager

    class Runner:
        async def run_stream(self, job, messages, persona, tools=None):
            yield AgentEvent(type=AgentEventType.DELTA, id=job.msg_id, delta="Postgres it is.")

    async def fake_persona(_): return persona()
    async def fake_history(**_): return []
    async def fake_resolve(_, __=()): return "text", None
    seen = {}

    async def fake_remember(j, p, reply):
        seen["reply"] = reply
        return 3
    monkeypatch.setattr(agentic_manager.nucleus_client, "resolve_persona", fake_persona)
    monkeypatch.setattr(agentic_manager.nucleus_client, "fetch_history", fake_history)
    monkeypatch.setattr(agentic_manager, "resolve_output_spec", fake_resolve)
    monkeypatch.setattr(agentic_manager, "remember", fake_remember)
    monkeypatch.setattr(agentic_manager.NewImprovedPromptBuilder, "build", lambda self, **kw: _empty())
    manager = NewImprovedAgenticManager(runner=Runner(), embedder=None, store=None)
    events = [e async for e in manager.run(job())]
    done = next(e for e in events if e.type == AgentEventType.END)
    assert done.recalled == 3 and seen["reply"] == "Postgres it is."


async def _empty():
    return []


def test_the_payload_s_recall_flag_is_read():
    data = {"id": "pe1", "name": "Sara", "prompt": {"system_prompt": "hi"}, "capabilities": [], "mcp_servers": [],
            "model": {"provider": "openai", "model_id": "gpt-4o", "api_key": "k"}}
    assert persona_from(data).recall_enabled is True
    assert persona_from({**data, "recall_enabled": False}).recall_enabled is False
    assert project_id_of(job()) == "p1"
