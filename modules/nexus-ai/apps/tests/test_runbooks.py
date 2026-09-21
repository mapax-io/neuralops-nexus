"""
W6 Runbooks: a step's job carries the previous step's reply; it joins the
persona prompt as its own block, after the routine's, clipped to its head.
"""
from apps.managers.routines import ROUTINE_HEADING, RoutineConfig, apply_routine
from apps.managers.runbooks import CLIP_NOTE, STEP_HEADING, apply_step_context
from apps.schemas.trigger import ModelConfig, PersonaCapabilities, PersonaConfig, TriggerJob


def persona() -> PersonaConfig:
    return PersonaConfig(id="pe1", name="Sara", system_prompt="You are Sara.", model=ModelConfig(provider="openai", model_id="gpt-4o-mini"), mcp_servers=[], capabilities=PersonaCapabilities())


def test_the_previous_reply_joins_the_prompt_after_the_routine_block():
    p = apply_routine(persona(), RoutineConfig(id="r1", name="digest", title="Digest", instructions="Summarise."))
    out = apply_step_context(p, "  Revenue was up 4%.  ")
    assert out.system_prompt == f"You are Sara.\n\n{ROUTINE_HEADING.format(title='Digest')}\nSummarise.\n\n{STEP_HEADING}\nRevenue was up 4%."
    assert out.model == p.model  # nothing else moves
    assert persona().system_prompt == "You are Sara."  # the persona itself is untouched


def test_a_long_reply_is_clipped_to_its_head_and_says_so(monkeypatch):
    from apps.core.config import settings
    monkeypatch.setattr(settings, "RUNBOOK_STEP_CONTEXT_MAX", 20)
    out = apply_step_context(persona(), "x" * 19 + " tail that goes on and on")
    assert out.system_prompt.endswith(f"{STEP_HEADING}\n{'x' * 19}{CLIP_NOTE}")


def test_an_empty_context_leaves_the_persona_alone_and_the_job_carries_the_field():
    p = persona()
    assert apply_step_context(p, "   ") is p
    job = TriggerJob(job_id="j", msg_id="m", persona_id="pe1", topic_id="t", user_message_id="u", message="go", step_context="earlier")
    assert job.step_context == "earlier"
    assert TriggerJob(job_id="j", msg_id="m", persona_id="pe1", topic_id="t", user_message_id="u", message="go").step_context is None
