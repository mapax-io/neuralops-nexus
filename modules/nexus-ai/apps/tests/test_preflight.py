"""
W3 Preflight: a persona that proposes before acting runs its first turn with
no tools and answers in the `preflight` output type; nucleus asks a person,
then re-triggers with the approved plan and the tools back on. The worker
owns the "would this run use tools" judgement -- nucleus never reads
capability configs.
"""
from apps.managers.preflight import PLAN_HEADING, plan_turn
from apps.output_types import OutputTypeRegistry
from apps.schemas.trigger import (
    MCPArgs, ModelConfig, PersonaCapabilities, PersonaConfig, Shell, TriggerJob, WebSearchArgs,
)


def persona(**over) -> PersonaConfig:
    base = dict(
        id="pe1", name="Sara", system_prompt="You are Sara.",
        model=ModelConfig(provider="openai", model_id="gpt-4o-mini"),
        mcp_servers=[], capabilities=PersonaCapabilities(),
    )
    base.update(over)
    return PersonaConfig(**base)


def job(**over) -> TriggerJob:
    base = dict(job_id="j", msg_id="m", persona_id="pe1", topic_id="t", user_message_id="u", message="do it")
    base.update(over)
    return TriggerJob(**base)


def test_the_preflight_output_type_is_registered_with_its_contract():
    spec = OutputTypeRegistry.get("preflight")
    assert spec is not None and spec.render_as == "preflight"
    for key in ("<<<OUTPUT:preflight>>>", '"summary"', '"steps"', '"risks"', '"writes"'):
        assert key in spec.system_instruction
    assert spec.example_prompts == []  # never auto-classified; only nucleus's gate selects it


def test_a_gated_persona_with_acting_tools_gets_a_toolless_preflight_turn():
    p = persona(mcp_servers=[MCPArgs(url="http://tools.test")], capabilities=PersonaCapabilities(shell=Shell()))
    run_persona, output_type = plan_turn(job(preflight=True), p)
    assert output_type == "preflight"
    assert run_persona.mcp_servers == [] and run_persona.capabilities == PersonaCapabilities()
    assert run_persona.system_prompt == p.system_prompt  # nothing else moves


def test_read_only_capabilities_do_not_count_as_acting():
    p = persona(capabilities=PersonaCapabilities(web_search=WebSearchArgs()))
    run_persona, output_type = plan_turn(job(preflight=True, output_type="chart"), p)
    assert output_type == "chart" and run_persona is p


def test_an_ungated_run_is_untouched():
    p = persona(mcp_servers=[MCPArgs(url="http://tools.test")])
    run_persona, output_type = plan_turn(job(output_type="auto"), p)
    assert output_type == "auto" and run_persona is p


def test_an_approved_plan_rides_ahead_of_the_prompt_with_the_tools_kept():
    p = persona(mcp_servers=[MCPArgs(url="http://tools.test")])
    run_persona, output_type = plan_turn(job(approved_plan="1. Read the CSV\n2. Write the report"), p)
    assert output_type == "auto"
    assert run_persona.mcp_servers == p.mcp_servers
    assert run_persona.system_prompt.startswith(f"{PLAN_HEADING}\n1. Read the CSV\n2. Write the report\n\n")
    assert run_persona.system_prompt.endswith("You are Sara.")
