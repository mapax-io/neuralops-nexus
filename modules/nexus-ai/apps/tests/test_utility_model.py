"""
W17: the server's utility model rides on the persona payload; the worker's
own small passes ask utility_model_for(persona) and get the persona's model
back when the server has none.
"""
from apps.managers.nucleus_client import persona_from, utility_model_for


def payload(**over):
    base = {
        "id": "pe1",
        "name": "Sara",
        "prompt": {"system_prompt": "You are Sara.", "output_type": "text", "context_scope": None},
        "model": {"provider": "anthropic", "model_id": "claude-sonnet-5", "api_key": "big-key", "max_tokens": 4096, "temperature": 0.3},
        "mcp_servers": [],
        "capabilities": [],
        "temperature": 0.3,
        "max_tokens": 4096,
        "max_steps": 4,
    }
    base.update(over)
    return base


def test_the_utility_model_maps_with_its_own_key_and_settings():
    persona = persona_from(payload(utility_model={"provider": "openai", "model_id": "gpt-4o-mini", "api_key": "small-key", "max_tokens": 1024}))
    assert persona.utility_model is not None
    assert (persona.utility_model.provider, persona.utility_model.model_id, persona.utility_model.api_key) == ("openai", "gpt-4o-mini", "small-key")
    assert utility_model_for(persona) is persona.utility_model


def test_no_utility_model_falls_back_to_the_personas_own():
    persona = persona_from(payload())
    assert persona.utility_model is None
    assert utility_model_for(persona) is persona.model
    older = persona_from({k: v for k, v in payload().items()})  # an older nucleus sends no key at all
    assert utility_model_for(older).model_id == "claude-sonnet-5"
