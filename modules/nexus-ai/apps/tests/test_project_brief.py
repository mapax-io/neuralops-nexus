"""
The Project Brief rides ahead of the persona prompt: nucleus ships it on the
persona payload, the worker composes it into the system prompt at the boundary
so every runner and prompt path sees one string, brief first.
"""
from apps.managers.nucleus_client import persona_from
from apps.managers.prompt_builder import compose_system_prompt


def payload(**over):
    base = {
        "id": "pe1",
        "name": "Sara",
        "prompt": {"system_prompt": "You are Sara.", "output_type": "text", "context_scope": None},
        "model": {"provider": "openai", "model_id": "gpt-4o-mini", "api_key": "k", "max_tokens": 512, "temperature": 0.2},
        "mcp_servers": [],
        "capabilities": [],
        "temperature": 0.2,
        "max_tokens": 512,
        "max_steps": 4,
    }
    base.update(over)
    return base


def test_the_brief_comes_first_in_its_own_block():
    out = compose_system_prompt("Always answer in bullet points.", "You are Sara.")
    assert out == "Project brief — applies to every reply in this project:\nAlways answer in bullet points.\n\nYou are Sara."


def test_no_brief_leaves_the_persona_prompt_untouched():
    assert compose_system_prompt(None, "You are Sara.") == "You are Sara."
    assert compose_system_prompt("   \n", "You are Sara.") == "You are Sara."


def test_the_persona_payload_composes_the_brief_into_the_system_prompt():
    persona = persona_from(payload(project_brief="Ship the Q4 launch."))
    assert persona.system_prompt.startswith("Project brief — applies to every reply in this project:\nShip the Q4 launch.")
    assert persona.system_prompt.endswith("You are Sara.")


def test_an_older_nucleus_without_the_field_still_maps():
    persona = persona_from(payload())
    assert persona.system_prompt == "You are Sara."
    assert persona.name == "Sara"
