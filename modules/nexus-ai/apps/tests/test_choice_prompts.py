"""
W14 Choice prompts: on an ordinary text turn the model may answer with a
small set of options for the person to pick from. Nobody types @choice --
the text type's own instruction says when it is allowed, and a reply that
carries the choice markers resolves to the choice type like any other.
"""
from apps.managers.prompt_builder import with_output_instruction
from apps.output_types import OutputTypeRegistry
from apps.output_types.recovery import finalise_reply


def test_choice_is_registered_with_its_contract_and_never_auto_classified():
    spec = OutputTypeRegistry.get("choice")
    assert spec is not None and spec.render_as == "choice"
    for key in ("<<<OUTPUT:choice>>>", '"question"', '"options"', '"multiple"', '"hint"'):
        assert key in spec.system_instruction
    assert spec.example_prompts == []


def test_every_ordinary_turn_carries_the_choice_exception_but_a_plan_or_a_choice_does_not():
    for name in ("text", "chart", "code"):
        prompt = with_output_instruction("You are Sara.", OutputTypeRegistry.get(name).system_instruction)
        assert prompt.startswith("You are Sara.\n\n--- OUTPUT FORMAT INSTRUCTION ---\n")
        assert "<<<OUTPUT:choice>>>" in prompt and "genuinely" in prompt
    for name in ("preflight", "choice"):
        prompt = with_output_instruction("You are Sara.", OutputTypeRegistry.get(name).system_instruction)
        assert "genuinely" not in prompt
    assert with_output_instruction("You are Sara.", None) == "You are Sara."


def test_a_text_turn_that_answers_with_the_choice_markers_resolves_as_a_choice():
    raw = '<<<OUTPUT:choice>>>\n{"question": "Which region?", "options": [{"id": "na", "label": "North America"}], "multiple": false}\n<<<END_OUTPUT>>>'
    clean, final_type, render_as, _ = finalise_reply(raw, "text")
    assert (final_type, render_as) == ("choice", "choice")
    assert clean.startswith("{") and '"question"' in clean


# ── a pick's turn resolves like the request that raised the question ─────────
# The pick ("@Faisal → Last 10 years") says nothing about charts, so classified
# on its own it is plain text; the model then answers the original request with
# an unmarked chart that the app shows as a code block. The turn the pick
# unlocks belongs to the request that produced the choice.
import pytest

from apps.output_types.resolver import request_behind_pick, resolve_output_spec
from apps.schemas.trigger import HistoryMessage, TriggerJob

CLASSIFIER = "apps.output_types.classifier.classify_output_type"
REQUEST = "give me a line chart of Canada's inflation, but ask me which time span first"
CHOICE = '{"question": "Which time span?", "options": [{"id": "5y", "label": "Last 5 years"}], "multiple": false}'


def pick_job(message="@Faisal → Last 10 years", output_type="auto"):
    return TriggerJob(job_id="j1", msg_id="m1", persona_id="p1", topic_id="t1", user_message_id="u1", message=message, output_type=output_type)


def user(content):
    return HistoryMessage(role="user", content=content)


def choice():
    return HistoryMessage(role="assistant", content=CHOICE, output_type="choice")


def test_the_request_behind_a_pick_is_the_user_message_before_the_last_choice():
    history = [user("hello"), HistoryMessage(role="assistant", content="hi"), user(REQUEST), choice()]
    assert request_behind_pick("@Faisal → Last 10 years", history) == REQUEST
    assert request_behind_pick("→ Last 10 years", history) == REQUEST


def test_chained_picks_still_resolve_to_the_first_request():
    history = [user(REQUEST), choice(), user("@Faisal → GDP growth"), choice()]
    assert request_behind_pick("@Faisal → Last 10 years", history) == REQUEST


def test_an_ordinary_message_is_not_a_pick():
    history = [user(REQUEST), choice()]
    assert request_behind_pick("A → B is a mapping, explain it", history) is None
    assert request_behind_pick("no arrow here", history) is None


def test_a_pick_with_nothing_to_go_back_to_stands_on_its_own():
    assert request_behind_pick("→ Last 10 years", []) is None
    assert request_behind_pick("→ Last 10 years", [choice()]) is None
    # picks all the way back: nobody ever asked for anything
    assert request_behind_pick("→ B", [user("→ A"), choice()]) is None


@pytest.mark.asyncio
async def test_a_pick_is_classified_from_its_request_not_its_own_words(monkeypatch):
    seen = []

    async def fake(prompt):
        seen.append(prompt)
        return "chart"
    monkeypatch.setattr(CLASSIFIER, fake)

    name, spec = await resolve_output_spec(pick_job(), [user(REQUEST), choice()])

    assert seen == [REQUEST]
    assert (name, spec.render_as) == ("chart", "chart")


@pytest.mark.asyncio
async def test_a_pick_without_a_request_behind_it_is_classified_as_itself(monkeypatch):
    seen = []

    async def fake(prompt):
        seen.append(prompt)
        return "text"
    monkeypatch.setattr(CLASSIFIER, fake)

    await resolve_output_spec(pick_job(), [])

    assert seen == ["@Faisal → Last 10 years"]


@pytest.mark.asyncio
async def test_an_explicit_type_still_wins_for_a_pick(monkeypatch):
    async def boom(_):
        raise AssertionError("classifier must not run for an explicit type")
    monkeypatch.setattr(CLASSIFIER, boom)

    name, _ = await resolve_output_spec(pick_job(output_type="table"), [user(REQUEST), choice()])

    assert name == "table"


# ── an unmarked choice is still a choice ─────────────────────────────────────
# Live, the model answered the choice contract to the letter and dropped the
# markers, so the reply was filed as text and the app showed raw JSON. The
# exception is on every ordinary turn, so a reply that IS a choice prompt is
# recovered as one whatever type the turn resolved to -- except a preflight
# turn, whose instruction never offered it.
CHOICE_JSON = '{ "question": "Annual or quarterly?", "options": [ { "id": "annual", "label": "Annual" }, { "id": "q", "label": "Quarterly" } ], "multiple": false }'


def test_an_unmarked_choice_on_a_text_turn_is_recovered_as_a_choice():
    clean, final_type, render_as, _ = finalise_reply(CHOICE_JSON, "text")
    assert (final_type, render_as, clean) == ("choice", "choice", CHOICE_JSON)


def test_an_unmarked_choice_on_a_chart_turn_is_recovered_too():
    _, final_type, render_as, _ = finalise_reply(CHOICE_JSON + "\n<<<END_OUTPUT>>", "chart")
    assert (final_type, render_as) == ("choice", "choice")


def test_a_preflight_turn_never_recovers_a_choice():
    _, final_type, _, _ = finalise_reply(CHOICE_JSON, "preflight")
    assert final_type == "text"


def test_recovery_needs_the_choice_shape_and_nothing_around_it():
    _, final_type, _, _ = finalise_reply("Quick question: " + CHOICE_JSON, "text")
    assert final_type == "text"
    _, final_type, _, _ = finalise_reply('{"question": "Which?", "options": "annual or quarterly"}', "text")
    assert final_type == "text"
    _, final_type, _, _ = finalise_reply('{"question": "Which?", "options": []}', "text")
    assert final_type == "text"
    # a chart-shaped reply on a text turn stays text: the chart was never asked for
    _, final_type, _, _ = finalise_reply('{"type": "bar", "datasets": [], "labels": []}', "text")
    assert final_type == "text"
