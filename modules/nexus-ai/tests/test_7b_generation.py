"""
7b (owner's ruling 2026-10-20): generation settings are MODEL properties.
Pins the nucleus_client mapping — each ModelSpec carries its own
max_output_tokens / temperature / routing_notes, and an OLDER nucleus
(no per-model fields) falls back to the persona-level legacy numbers.
"""
from ai_engine.core.nucleus_client import persona_from
from ai_engine.core.specs import ModelRole


def _model(mid: str, **over) -> dict:
    base = {
        "id": f"cfg-{mid}", "name": mid, "provider": "openai", "model_id": mid,
        "qualified_id": f"openai:{mid}", "api_base": None, "api_key": "sk-test",
        "context_window": 128000, "supports_tools": True,
        "supports_streaming": True, "supports_vision": False,
    }
    base.update(over)
    return base


def _persona(**over) -> dict:
    base = {
        "id": "per-1", "name": "Seaty",
        "prompt": {"system_prompt": "You answer.", "output_type": "text"},
        "model": _model("gpt-4o"),
        "temperature": 0.3, "max_tokens": 4096, "max_steps": 10,
    }
    base.update(over)
    return base


def test_7b1_each_spec_carries_its_own_generation_numbers():
    data = _persona(
        model=_model("gpt-4o", max_output_tokens=16000, temperature=0.7),
        fallback_models=[_model("deepseek-chat", provider="deepseek",
                                max_output_tokens=8000, temperature=0.2,
                                routing_notes="cheap, good for summaries")],
    )
    persona = persona_from(data, company_id="c1", project_id="p1")
    primary = persona.model_for(ModelRole.STANDARD)
    assert primary.max_output_tokens == 16000
    assert primary.temperature == 0.7
    fallback = [m for m in persona.models if m.role is ModelRole.FALLBACK][0]
    # The candidate with the smaller ceiling keeps ITS OWN numbers — it never
    # borrows the primary's 16K (the whole point of 7b).
    assert fallback.max_output_tokens == 8000
    assert fallback.temperature == 0.2
    assert fallback.routing_notes == "cheap, good for summaries"


def test_7b2_an_older_nucleus_falls_back_to_the_persona_legacy_numbers():
    # No per-model generation fields anywhere — the persona-level values
    # stand in on EVERY seat, so nothing behaves differently than before.
    data = _persona(
        router_model=_model("gpt-4o-mini"),
        fallback_models=[_model("gpt-4.1")],
    )
    persona = persona_from(data, company_id="c1", project_id="p1")
    for spec in persona.models:
        assert spec.max_output_tokens == 4096
        assert spec.temperature == 0.3
        assert spec.routing_notes == ""
    # The legacy persona-level fields still carry the same values.
    assert persona.max_output_tokens == 4096
    assert persona.temperature == 0.3
