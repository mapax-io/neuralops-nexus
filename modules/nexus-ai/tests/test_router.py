"""
Layer 2, items 13 + 46 — the router stage and the escalate hand-over
(docs/NEXUS-AI-REVAMP.md §1.3 Layer 2 decisions; trial G, 2026-10-13).

Through the running service: a router answers simple questions itself; an
Escalate output hands the reply to the deep model (announced, billed apart,
hints become the topic's set); a broken router falls through; personas
without the seats behave exactly as before.
"""
from __future__ import annotations

import pytest

from conftest import openai_model
from fake_nucleus import make_persona

pytestmark = pytest.mark.asyncio


def _escalate_step(hints: list[str] | None = None) -> dict:
    return {"kind": "tool_call", "call_id": "call_esc", "name": "final_result",
            "args": {"task": "do the deep work", "summary": "user asked something hard",
                     "expected_output": "a full answer", "tool_hints": hints or []}}


def _router_persona(harness, **kw) -> dict:
    return make_persona(
        openai_model(harness),
        router_model=openai_model(harness, config_id="m-router", model_id="fake-router"),
        deep_model=openai_model(harness, config_id="m-deep", model_id="fake-deep"),
        **kw,
    )


async def test_r1_router_answers_simple_questions(harness):
    """Item 13 — a simple question is answered BY THE ROUTER, streamed live.
    The persona has a router seat; the router replies in text → that text is
    the reply (deltas stream, message_done carries it), exactly ONE model call
    happens, and its usage record says role=ROUTER, kind=router."""
    harness.nucleus.persona = _router_persona(harness)
    harness.provider.script.steps = [{"kind": "text", "text": "Tokyo is UTC+9."}]
    events = await harness.trigger()

    types = [e["type"] for e in events]
    assert "deep_escalation" not in types and types[-1] == "message_done"
    assert "message_delta" in types  # streamed live, not held back
    [done] = [e for e in events if e["type"] == "message_done"]
    assert "UTC+9" in done["content"]
    assert done["answered_by_model"] is None  # no hand-over happened
    assert len(harness.provider.requests) == 1
    records = await harness.wait_for_usage(1)
    assert records[0]["role"] == "ROUTER" and records[0]["kind"] == "router"


async def test_r2_escalation_hands_over_announced_and_billed_apart(harness):
    """Item 46 — the Escalate output hands the reply to the DEEP model.
    The router returns the hand-over struct → a deep_escalation event names the
    deep model → the deep run streams the real answer (its text is the saved
    content; the router's run contributes nothing to it) → message_done says
    answered_by_model=deep → TWO usage records: role=ROUTER then the reply."""
    harness.nucleus.persona = _router_persona(harness)
    harness.provider.script.steps = [
        _escalate_step(),
        {"kind": "text", "text": "Deep answer with full reasoning."},
    ]
    events = await harness.trigger()

    types = [e["type"] for e in events]
    assert "deep_escalation" in types and types[-1] == "message_done"
    assert types.index("deep_escalation") < types.index("message_done")
    [esc] = [e for e in events if e["type"] == "deep_escalation"]
    assert esc["escalated_to"] == "Fake openai"
    [done] = [e for e in events if e["type"] == "message_done"]
    assert "Deep answer" in done["content"]
    assert done["answered_by_model"] == "Fake openai"

    # the deep model received the router's hand-over note
    deep_req = harness.provider.requests[-1]
    import json as _json
    assert "do the deep work" in _json.dumps(deep_req["messages"])

    records = await harness.wait_for_usage(2)
    assert [r["role"] for r in records] == ["ROUTER", "DEEP"]
    assert records[0]["kind"] == "router" and records[1]["kind"] == "chat_reply"


async def test_r3_tool_hints_become_the_topic_set(harness, tmp_path):
    """Items 13+1 — on a topic's FIRST reply the router's tool_hints are the set.
    No topic_tools in the job; the router hints 'filesystem' → the deep run
    loads it (its schema is in the deep request) and message_done carries
    loaded_tools=['filesystem'] — the courier nucleus stores as topic_tools."""
    harness.nucleus.persona = _router_persona(
        harness,
        capabilities=[{"id": "cap1", "name": "defaults",
                       "capability_config": {"filesystem": {"root_dir": str(tmp_path)},
                                             "web_search": {"local": "duckduckgo"}}}],
    )
    harness.provider.script.steps = [
        _escalate_step(hints=["filesystem"]),
        {"kind": "text", "text": "Done with the files."},
    ]
    events = await harness.trigger()

    [done] = [e for e in events if e["type"] == "message_done"]
    assert done["loaded_tools"] == ["filesystem"]
    deep_req = harness.provider.requests[-1]
    names = [t["function"]["name"] for t in deep_req.get("tools", [])]
    assert any(n in names for n in ("read_file", "write_file"))  # filesystem loaded
    # the router itself ran WITHOUT tools (it hints, it doesn't act)
    router_req = harness.provider.requests[0]
    router_tool_names = [t["function"]["name"] for t in router_req.get("tools", [])]
    assert "read_file" not in router_tool_names


async def test_r4_router_failure_falls_through_to_standard(harness):
    """Item 13 — a broken router NEVER blocks the reply (source=router_failed).
    The router's model points at a dead endpoint (connection refused) → the
    reply falls through to the STANDARD model and finishes normally; the
    router's record is marked source=router_failed, the reply's is not."""
    from fake_nucleus import make_model
    persona = make_persona(
        openai_model(harness),
        router_model=make_model("openai", "http://127.0.0.1:9/v1",
                                config_id="m-router", model_id="fake-router"),
        deep_model=openai_model(harness, config_id="m-deep", model_id="fake-deep"),
    )
    harness.nucleus.persona = persona
    harness.provider.script.text = "Standard answered after the router died."
    events = await harness.trigger()

    types = [e["type"] for e in events]
    assert types[-1] == "message_done" and "message_error" not in types
    records = await harness.wait_for_usage(2)
    assert records[0]["role"] == "ROUTER" and records[0]["source"] == "router_failed"
    assert records[1]["role"] == "STANDARD" and records[1]["source"] is None


async def test_r5_standard_escalates_when_no_router_seat(harness):
    """Item 13 amendment — no router seat, but a DEEP seat: STANDARD can hand over.
    The standard model runs first (full reply rights) and returns Escalate →
    the deep model answers; both billed under their own roles."""
    harness.nucleus.persona = make_persona(
        openai_model(harness),
        deep_model=openai_model(harness, config_id="m-deep", model_id="fake-deep"),
    )
    harness.provider.script.steps = [
        _escalate_step(),
        {"kind": "text", "text": "Deep took over."},
    ]
    events = await harness.trigger()
    types = [e["type"] for e in events]
    assert "deep_escalation" in types and types[-1] == "message_done"
    records = await harness.wait_for_usage(2)
    assert [r["role"] for r in records] == ["STANDARD", "DEEP"]


def _bench_models(harness) -> list[dict]:
    """Two deep models with their own names and strengths notes — the smart
    router's bench (make_model names every model 'Fake openai', so the names
    are overridden to make the pick observable)."""
    return [
        {**openai_model(harness, config_id="m-deep1", model_id="fake-deep1"),
         "name": "Deep One", "routing_notes": "general reasoning"},
        {**openai_model(harness, config_id="m-deep2", model_id="fake-deep2"),
         "name": "Deep Two", "routing_notes": "best for code"},
    ]


async def test_r7_the_router_picks_from_the_bench_by_name(harness):
    """Smart router (ruled 2026-10-20) — the deep seat is a BENCH and the
    router NAMES its pick. The router's request carries the bench listing
    (names + routing_notes); Escalate.target_model='Deep Two' → the SECOND
    bench model runs the deep turn, is announced, and bills under its own
    model_id."""
    harness.nucleus.persona = make_persona(
        openai_model(harness),
        router_model=openai_model(harness, config_id="m-router", model_id="fake-router"),
        deep_models=_bench_models(harness),
    )
    harness.provider.script.steps = [
        {"kind": "tool_call", "call_id": "call_esc", "name": "final_result",
         "args": {"task": "write the code", "target_model": "Deep Two"}},
        {"kind": "text", "text": "Code from the named pick."},
    ]
    events = await harness.trigger()

    [esc] = [e for e in events if e["type"] == "deep_escalation"]
    assert esc["escalated_to"] == "Deep Two"
    [done] = [e for e in events if e["type"] == "message_done"]
    assert done["answered_by_model"] == "Deep Two"
    assert harness.provider.requests[-1]["model"] == "fake-deep2"
    # the router was TOLD the bench — both names and the notes ride its request
    import json as _json
    router_blob = _json.dumps(harness.provider.requests[0])
    assert "Deep One" in router_blob and "best for code" in router_blob
    records = await harness.wait_for_usage(2)
    assert records[1]["role"] == "DEEP" and records[1]["model_id"] == "fake-deep2"


async def test_r8_an_invalid_pick_falls_back_to_the_benchs_first(harness):
    """Smart router — a garbage (or missing) target_model never breaks the
    hand-over: the bench's FIRST model is the default pick."""
    harness.nucleus.persona = make_persona(
        openai_model(harness),
        router_model=openai_model(harness, config_id="m-router", model_id="fake-router"),
        deep_models=_bench_models(harness),
    )
    harness.provider.script.steps = [
        {"kind": "tool_call", "call_id": "call_esc", "name": "final_result",
         "args": {"task": "something hard", "target_model": "No Such Model"}},
        {"kind": "text", "text": "The default pick answered."},
    ]
    events = await harness.trigger()
    [done] = [e for e in events if e["type"] == "message_done"]
    assert done["answered_by_model"] == "Deep One"
    assert harness.provider.requests[-1]["model"] == "fake-deep1"


async def test_r9_bench_mapping_pick_rules_and_older_nucleus_compat(harness):
    """The unit half of the smart router: an OLDER nucleus (single deep_model,
    no deep_models key) maps to a one-item bench; a bench of one gets the
    plain instructions (nothing to choose); picks match by name or model_id,
    case-insensitively, and fall back to the first."""
    from ai_engine.core.nucleus_client import persona_from
    from ai_engine.core.specs import ModelRole
    from ai_engine.pydantic_ai_system.escalation import Escalate, pick_deep_model, router_instructions

    old = make_persona(openai_model(harness),
                       deep_model=openai_model(harness, config_id="m-deep", model_id="fake-deep"))
    old.pop("deep_models")  # exactly what an older nucleus sends
    bench = persona_from(old, company_id="c", project_id="p").models_for(ModelRole.DEEP)
    assert [m.model_id for m in bench] == ["fake-deep"]
    assert "bench" not in router_instructions(bench)  # one model: no listing

    two = make_persona(openai_model(harness), deep_models=_bench_models(harness))
    bench2 = persona_from(two, company_id="c", project_id="p").models_for(ModelRole.DEEP)
    assert "Deep One: general reasoning" in router_instructions(bench2)
    assert pick_deep_model(Escalate(task="t", target_model="FAKE-DEEP2"), bench2).name == "Deep Two"
    assert pick_deep_model(Escalate(task="t", target_model="deep two"), bench2).name == "Deep Two"
    assert pick_deep_model(Escalate(task="t"), bench2).name == "Deep One"
    assert pick_deep_model(Escalate(task="t"), []) is None


async def test_r10_lane_standard_sends_ordinary_work_to_the_everyday_model(harness):
    """Three-way routing (ruled 2026-10-21, after "2+2" and an ordinary
    explainer both landed on the expensive bench): the router's Escalate with
    lane='standard' hands the work to the persona's EVERYDAY model — announced
    like any hand-over, billed under STANDARD — and the bench stays untouched.
    The router is TOLD the three lanes in its instructions."""
    harness.nucleus.persona = make_persona(
        openai_model(harness),
        router_model=openai_model(harness, config_id="m-router", model_id="fake-router"),
        deep_models=_bench_models(harness),
    )
    harness.provider.script.steps = [
        {"kind": "tool_call", "call_id": "call_esc", "name": "final_result",
         "args": {"task": "an ordinary question", "lane": "standard"}},
        {"kind": "text", "text": "The everyday model answered it."},
    ]
    events = await harness.trigger()

    types = [e["type"] for e in events]
    assert "deep_escalation" in types and types[-1] == "message_done"
    [esc] = [e for e in events if e["type"] == "deep_escalation"]
    assert esc["escalated_to"] == "Fake openai"  # the standard model's name, not a bench member's
    [done] = [e for e in events if e["type"] == "message_done"]
    assert "everyday model answered" in done["content"]
    assert done["answered_by_model"] == "Fake openai"
    # the reply ran on the persona's own model — neither bench member was dialed
    assert harness.provider.requests[-1]["model"] not in ("fake-deep1", "fake-deep2")
    # the router was told all three lanes
    import json as _json
    router_blob = _json.dumps(harness.provider.requests[0])
    assert "lane='standard'" in router_blob and "lane='deep'" in router_blob
    records = await harness.wait_for_usage(2)
    assert [r["role"] for r in records] == ["ROUTER", "STANDARD"]


async def test_r6_no_seats_means_yesterdays_behaviour(harness):
    """Item 13 — a persona with neither seat is untouched Layer 0/1.
    One STANDARD call, no escalation machinery on the wire: no Escalate tool in
    the request (only item 5's ask_user), no deep_escalation event, message_done as always."""
    harness.nucleus.persona = make_persona(openai_model(harness))
    events = await harness.trigger()
    types = [e["type"] for e in events]
    assert "deep_escalation" not in types and types[-1] == "message_done"
    body = harness.provider.requests[-1]
    # item 5's ask_user is the ONLY tool — no final_result/Escalate leaked
    names = [t["function"]["name"] for t in body.get("tools", [])]
    assert names == ["ask_user"]
    records = await harness.wait_for_usage(1)
    assert records[0]["role"] == "STANDARD"
