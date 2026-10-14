"""
Layer 3, items 24/44/33 — retrieval inside a reply, end to end
(docs/NEXUS-AI-REVAMP.md §1.3 Layer 3 decisions 9+10; built 2026-10-13).
The vector rows are seeded through the REAL embed endpoints (hash embedder),
then an ordinary /trigger reply retrieves them: always-search v1, threshold,
same-topic chat memory, the context_retrieved event, retrieved_sources on done.
Projects here get their own ids — triggers for other tests' projects have no
index and keep their exact pre-Layer-3 streams.
"""
from __future__ import annotations

import httpx
import pytest

from conftest import INTERNAL_KEY

pytestmark = pytest.mark.asyncio

HASH = {"provider": "hash", "model_id": "hash-768"}
PROJECT, COMPANY, TOPIC = "pr-vec", "c-vec", "t-vec"


def _by_type(events, kind):
    return [e for e in events if e["type"] == kind]


async def _seed(harness):
    async with httpx.AsyncClient(timeout=60.0) as client:
        headers = {"X-Internal-Key": INTERNAL_KEY}
        r = await client.post(f"{harness.app_url}/api/v1/embed/message/", headers=headers, json={
            "message_id": "tr-m1", "company_id": COMPANY, "sequence": 1,
            "topic_id": TOPIC, "channel_id": "ch", "project_id": PROJECT,
            "sender_id": "u1", "sender_name": "Noaman", "sender_type": "human",
            "content": "we picked pgbouncer for connection pooling",
            "created_at": "2026-10-13T00:00:00Z",
            "used_tools": ["github__search"], "embedder": HASH,
        })
        assert r.status_code == 200, r.text
        r = await client.post(f"{harness.app_url}/api/v1/embed/message/", headers=headers, json={
            "message_id": "tr-other-topic", "company_id": COMPANY, "sequence": 1,
            "topic_id": "t-elsewhere", "channel_id": "ch", "project_id": PROJECT,
            "sender_id": "u1", "sender_name": "Noaman", "sender_type": "human",
            "content": "secret pgbouncer pooling notes from another topic",
            "created_at": "2026-10-13T00:00:00Z", "embedder": HASH,
        })
        assert r.status_code == 200, r.text
        r = await client.post(f"{harness.app_url}/api/v1/embed/", headers=headers, json={
            "source_id": "tr-doc", "type": "file", "label": "pooling.md",
            "content": "pgbouncer connection pooling: what we pick and why. pgbouncer settings and sizing.",
            "project_id": PROJECT, "company_id": COMPANY, "embedder": HASH,
        })
        assert r.status_code == 200, r.text


def _job(harness, message):
    return harness.job(company_id=COMPANY, project_id=PROJECT, topic_id=TOPIC,
                       msg_id="msg-ret", message=message)


async def test_tr1_retrieval_event_section_and_sources(harness, vector_url):
    """Decisions 9+10 — a reply over an indexed project retrieves and says so.
    context_retrieved arrives BEFORE the text with references+scores only (no
    chunk text on the wire); the model's instructions carry the retrieved
    section with the chunk text and the used_tools note; message_done carries
    the same references as retrieved_sources, same-topic chat memory included."""
    await _seed(harness)
    harness.provider.script.text = "Pooling is handled by pgbouncer."
    events = await harness.trigger(_job(harness, "what did we pick for pgbouncer connection pooling?"))

    [retrieved] = _by_type(events, "context_retrieved")
    assert retrieved["count"] == len(retrieved["retrieved"]) >= 2
    ids = {r["id"] for r in retrieved["retrieved"]}
    assert "tr-m1" in ids and any(i.startswith("tr-doc:") for i in ids)
    assert "tr-other-topic" not in ids  # item 44: SAME topic only
    assert all("text" not in r for r in retrieved["retrieved"])  # refs only
    assert all(r["score"] > 0 for r in retrieved["retrieved"])
    assert events.index(retrieved) < events.index(_by_type(events, "message_done")[0])

    [done] = _by_type(events, "message_done")
    assert {r["id"] for r in done["retrieved_sources"]} == ids

    sent = harness.provider.requests[-1]
    instructions = str(sent)
    assert "Relevant project memory" in instructions
    assert "pgbouncer" in instructions
    assert "github__search" in instructions  # decision 6: what solved it travels


async def test_tr2_empty_project_stays_silent(harness, vector_url):
    """Decision 9 — no index means no event, no section, byte-same stream.
    A project that never embedded anything triggers no search chatter: zero
    context_retrieved events, retrieved_sources absent on message_done — the
    pre-Layer-3 stream shape, exactly ('otherwise db is empty for it')."""
    harness.provider.script.text = "Nothing to remember."
    events = await harness.trigger(harness.job(project_id="pr-no-index"))
    assert not _by_type(events, "context_retrieved")
    [done] = _by_type(events, "message_done")
    assert done.get("retrieved_sources") is None
    assert "Relevant project memory" not in str(harness.provider.requests[-1])


async def test_tr3_below_threshold_attaches_nothing(harness, vector_url):
    """Decision 9 — weak matches are thrown away, silently.
    The index HAS rows, but the message shares no tokens with them: every score
    lands under RETRIEVAL_MIN_SCORE, so nothing is attached and no event is
    emitted — an irrelevant memory never pollutes a reply."""
    await _seed(harness)
    harness.provider.script.text = "Unrelated answer."
    events = await harness.trigger(_job(
        harness, "zebra quantum violin marmalade xylophone"))
    assert not _by_type(events, "context_retrieved")
    [done] = _by_type(events, "message_done")
    assert done.get("retrieved_sources") is None
