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
    assert spec.render_as == "html"


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
