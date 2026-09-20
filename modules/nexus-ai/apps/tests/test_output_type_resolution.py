"""
Which output type a run uses, and the instruction the model is given for it.

Regression: the live path injected the classified type's NAME ("chart") as the
whole format instruction, so the model never saw the <<<OUTPUT:chart>>>
contract and invented its own chart -- ASCII art in a code fence, an SVG file
written to disk. It also ignored the explicit type nucleus sends for @chart.
"""
import pytest

from apps.output_types import OutputTypeRegistry
from apps.output_types.resolver import resolve_output_spec
from apps.schemas.trigger import ModelConfig, PersonaCapabilities, PersonaConfig, TriggerJob

CLASSIFIER = "apps.output_types.classifier.classify_output_type"


def job(message="give me a line chart for the Canadian economy", output_type="auto"):
    return TriggerJob(
        job_id="j1", msg_id="m1", persona_id="p1", topic_id="t1",
        user_message_id="u1", message=message, output_type=output_type,
    )


def persona():
    return PersonaConfig(
        id="pe1", name="Faisal", system_prompt="be brief",
        model=ModelConfig(id="mc1", provider="openai", model_id="gpt-4o-mini"),
        mcp_servers=[], capabilities=PersonaCapabilities(),
    )


@pytest.mark.asyncio
async def test_explicit_type_wins_without_consulting_the_classifier(monkeypatch):
    async def boom(_):
        raise AssertionError("classifier must not run when nucleus sent an explicit type")
    monkeypatch.setattr(CLASSIFIER, boom)

    name, spec = await resolve_output_spec(job(output_type="chart"))

    assert name == "chart"
    assert spec.render_as == "chart"  # drawn by the app, not framed as a page


@pytest.mark.asyncio
async def test_instruction_is_the_contract_not_the_bare_name():
    """The exact bug: the model was told 'chart' and nothing else."""
    _, spec = await resolve_output_spec(job(output_type="chart"))

    assert spec.system_instruction.strip() != "chart"
    assert "<<<OUTPUT:chart>>>" in spec.system_instruction
    assert "<<<END_OUTPUT>>>" in spec.system_instruction


@pytest.mark.asyncio
async def test_auto_consults_the_classifier(monkeypatch):
    async def fake(_):
        return "table"
    monkeypatch.setattr(CLASSIFIER, fake)

    name, spec = await resolve_output_spec(job(output_type="auto"))

    assert name == "table"
    assert spec is OutputTypeRegistry.get("table")


@pytest.mark.asyncio
async def test_unknown_explicit_type_falls_back_to_classification(monkeypatch):
    async def fake(_):
        return "terminal"
    monkeypatch.setattr(CLASSIFIER, fake)

    name, _ = await resolve_output_spec(job(output_type="banana"))

    assert name == "terminal"


@pytest.mark.asyncio
async def test_classified_name_with_no_registered_spec_falls_back_to_text(monkeypatch):
    """A name we cannot hand the model an instruction for is not usable."""
    async def fake(_):
        return "spreadsheet"  # nothing registers this
    monkeypatch.setattr(CLASSIFIER, fake)

    name, spec = await resolve_output_spec(job())

    assert name == "text"
    assert spec is OutputTypeRegistry.get("text")


@pytest.mark.asyncio
async def test_classifier_failure_falls_back_to_the_text_SPEC_not_the_word(monkeypatch):
    async def boom(_):
        raise RuntimeError("embedder down")
    monkeypatch.setattr(CLASSIFIER, boom)

    name, spec = await resolve_output_spec(job())

    assert name == "text"
    assert spec is OutputTypeRegistry.get("text")
    assert spec.system_instruction.strip() != "text"


@pytest.mark.asyncio
async def test_builder_puts_the_contract_in_the_system_prompt():
    from apps.managers.prompt_builder import NewImprovedPromptBuilder

    spec = OutputTypeRegistry.get("chart")
    messages = await NewImprovedPromptBuilder().build(
        job=job(output_type="chart"), persona=persona(), history=[],
        output_type_instruction=spec.system_instruction,
    )

    system = "".join(
        part.content for part in messages[0].parts if hasattr(part, "content")
    )
    assert "<<<OUTPUT:chart>>>" in system
    # the bug shape: an OUTPUT FORMAT INSTRUCTION section whose body is one word
    assert "--- OUTPUT FORMAT INSTRUCTION ---\nchart" not in system


# `@code` was offered by the composer and accepted by nucleus
# (_OUTPUT_TYPE_KEYWORDS) but registered nowhere here, so it resolved to
# unknown and silently fell back to classification.
@pytest.mark.asyncio
async def test_code_resolves_to_a_real_spec():
    name, spec = await resolve_output_spec(job(output_type="code"))

    assert name == "code"
    assert spec.render_as == "code"
    assert "<<<OUTPUT:code>>>" in spec.system_instruction


def test_registry_covers_every_directive_the_other_side_offers():
    """
    nucleus's _OUTPUT_TYPE_KEYWORDS and the composer's OUTPUT_DIRECTIVES offer
    exactly these eight. A name missing here resolves to unknown and the user's
    directive silently does nothing.
    """
    assert set(OutputTypeRegistry.names()) == {
        "text", "html", "chart", "table", "diagram", "form", "terminal", "code",
    }


def test_code_is_explicit_only_and_never_auto_classified():
    """
    The frontend renders this type as a bare <pre> -- the whole reply becomes a
    code block with no prose. That is right when the user typed @code and wrong
    for an ordinary "how do I..." question, so the spec carries no example
    prompts and the classifier builds no centroid for it.
    """
    assert OutputTypeRegistry.get("code").example_prompts == []


def test_code_forbids_markdown_fences():
    """CodeBlock renders content raw; a fence would show as literal backticks."""
    instruction = OutputTypeRegistry.get("code").system_instruction.lower()
    assert "no markdown" in instruction


# The chart type used to have the model write a complete Chart.js HTML page,
# framed by the app in a sandboxed iframe. It now emits a small description
# the app renders natively (neuralops-nexus-web-app: ChartBlock), which is
# 5-10x fewer tokens per chart, themed, and free of script execution.
def test_chart_renders_natively_from_a_description():
    spec = OutputTypeRegistry.get("chart")
    assert spec.render_as == "chart"
    instruction = spec.system_instruction
    assert "<<<OUTPUT:chart>>>" in instruction and "<<<END_OUTPUT>>>" in instruction
    for key in ('"type"', '"title"', '"labels"', '"datasets"', '"basis"'):
        assert key in instruction, f"the instruction must show the {key} key"
    assert "<!DOCTYPE" not in instruction and "Chart.js" not in instruction and "<canvas" not in instruction


def test_chart_instruction_states_the_guard_limits():
    """What the app's guard rejects, the model must be told up front."""
    instruction = OutputTypeRegistry.get("chart").system_instruction
    assert "6" in instruction          # datasets / slices cap
    assert "200" in instruction        # points cap
    assert "y axis" in instruction.lower() or "y-axis" in instruction.lower()
    assert "recalled" in instruction and "provided" in instruction and "tool" in instruction


def test_chart_instruction_covers_every_chart_js_type():
    """The app renders every kind chart.js ships; the model must be offered each one."""
    instruction = OutputTypeRegistry.get("chart").system_instruction
    for kind in ("line", "bar", "pie", "doughnut", "polarArea", "radar", "scatter", "bubble", "mixed"):
        assert f'"{kind}"' in instruction, kind
    assert '"r": number' in instruction     # bubble points
    assert "one name per" in instruction    # bubble names are required
    for key in ('"groups"', '"subtitle"', '"prefix"', '"suffix"', '"legend"', '"cutout"', '"gauge"', '"stepped"', '"pointStyle"', '"scale"'):
        assert key in instruction, key
    assert "logarithmic" in instruction and "[low, high]" in instruction and "null is a gap" in instruction
    assert '"color"' in instruction and '"colors"' in instruction
    assert '"charts"' in instruction  # several charts in one reply


# A model can follow the description exactly and still drop the markers around
# it. Without markers the reply reads as plain text and the app shows raw JSON
# as a paragraph. The worker recovers such a reply as the chart it is.
from apps.output_types.recovery import recover_unmarked

DESCRIPTION = '{"type": "bar", "title": "Sales", "labels": ["Q1"], "datasets": [{"label": "s", "data": [1]}]}'


def test_an_unmarked_chart_description_is_recovered_as_a_chart():
    assert recover_unmarked("chart", DESCRIPTION) == "chart"
    assert recover_unmarked("chart", "  " + DESCRIPTION + "\n") == "chart"


def test_recovery_needs_a_description_shape_not_just_json():
    assert recover_unmarked("chart", '{"name": "config", "value": 3}') is None
    assert recover_unmarked("chart", "Here is your chart: " + DESCRIPTION) is None
    assert recover_unmarked("chart", "not json") is None


def test_recovery_only_applies_when_a_chart_was_asked_for():
    assert recover_unmarked("text", DESCRIPTION) is None


def test_a_reply_of_several_charts_is_recovered_too():
    wrapper = '{"charts": [' + DESCRIPTION + ', ' + DESCRIPTION + ']}'
    assert recover_unmarked("chart", wrapper) == "chart"
    assert recover_unmarked("chart", '{"charts": []}') is None
    assert recover_unmarked("chart", '{"charts": [{"name": "x"}]}') is None


def test_recovery_ignores_a_stray_closing_marker():
    """A model that emits only <<<END_OUTPUT>>> has still written the chart."""
    assert recover_unmarked("chart", DESCRIPTION + " <<<END_OUTPUT>>>") == "chart"
    assert recover_unmarked("chart", "<<<OUTPUT:chart>>>\n" + DESCRIPTION) == "chart"


# Models mangle delimiters at token boundaries: "<<<END_OUTPUT>>" (two brackets),
# "<<OUTPUT:chart>>>", or no closer at all. A live reply was filed as text over a
# single missing ">". The parser matches the intent, not the exact bytes.
from apps.output_types.markers import parse_output_markers


def test_markers_tolerate_a_mangled_closer():
    clean, kind, _ = parse_output_markers("<<<OUTPUT:chart>>>\n" + DESCRIPTION + "\n<<<END_OUTPUT>>")
    assert kind == "chart"
    assert clean == DESCRIPTION


def test_markers_tolerate_a_mangled_opener_and_a_missing_closer():
    clean, kind, _ = parse_output_markers("<<OUTPUT:chart>>>\n" + DESCRIPTION)
    assert kind == "chart"
    assert clean == DESCRIPTION


def test_recovery_strips_mangled_stray_markers_too():
    assert recover_unmarked("chart", DESCRIPTION + " <<<END_OUTPUT>>") == "chart"


# A marker mentioned in prose is a mention, not a block. The contract puts the
# opener on the very first line; tolerance for a missing closer must not let a
# sentence like this be filed as a chart (a live reply was reduced to "` format.").
def test_a_marker_mentioned_mid_sentence_is_not_a_block():
    prose = "Sure — I will answer in the `<<<OUTPUT:chart>>>` format. What region?"
    clean, kind, _ = parse_output_markers(prose)
    assert kind == "text"
    assert clean == prose


def test_a_block_may_start_after_leading_prose_lines_but_on_its_own_line():
    clean, kind, _ = parse_output_markers("Here you go:\n<<<OUTPUT:chart>>>\n" + DESCRIPTION + "\n<<<END_OUTPUT>>>")
    assert kind == "chart"
    assert clean == DESCRIPTION


# ── one ending for every path ─────────────────────────────────────────────────
from apps.output_types.recovery import finalise_reply  # noqa: E402

CHART_JSON = '{"type": "bar", "title": "Sales", "labels": ["Q1"], "datasets": [{"label": "Sales", "data": [1]}]}'


def test_finalise_marked_chart_renders_as_chart():
    clean, kind, render_as, embed = finalise_reply(f"<<<OUTPUT:chart>>>\n{CHART_JSON}\n<<<END_OUTPUT>>>", "chart")
    assert (kind, render_as, embed) == ("chart", "chart", None)
    assert clean == CHART_JSON


def test_finalise_unmarked_chart_is_recovered_when_a_chart_was_asked_for():
    clean, kind, render_as, _ = finalise_reply(CHART_JSON, "chart")
    assert (kind, render_as, clean) == ("chart", "chart", CHART_JSON)


def test_finalise_a_conversational_reply_is_text_whatever_was_asked_for():
    clean, kind, render_as, embed = finalise_reply("Sorry, I have no figures for that.", "chart")
    assert (kind, render_as, embed) == ("text", "text", None)
    assert clean == "Sorry, I have no figures for that."


def test_finalise_keeps_the_embed_description_only_for_rich_output():
    raw = "<<<EMBED>>>a page about sales<<<END_EMBED>>>\n<<<OUTPUT:html>>>\n<html></html>\n<<<END_OUTPUT>>>"
    clean, kind, render_as, embed = finalise_reply(raw, "html")
    assert (kind, render_as, embed, clean) == ("html", "html", "a page about sales", "<html></html>")
    _, _, _, embed_text = finalise_reply("<<<EMBED>>>x<<<END_EMBED>>>\nplain words", "text")
    assert embed_text is None

