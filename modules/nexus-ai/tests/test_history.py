"""
T13 — the history rules, each one exercised, order kept (§1.5 behaviour rules).
"""
from __future__ import annotations

from ai_engine.context.history_policy import HistoryPolicy
from ai_engine.core.specs import HistoryRow, ModelRole, ModelSpec, PersonaSpec


def _persona(name: str = "NeuralBot") -> PersonaSpec:
    model = ModelSpec(
        role=ModelRole.STANDARD, config_id="m1", name="fake", provider="openai",
        model_id="fake", base_url=None, api_key=None, context_window=100_000,
        supports_tools=True, supports_streaming=True, supports_vision=False,
    )
    return PersonaSpec(
        id="p1", name=name, company_id="c", project_id="pr",
        system_prompt="sp", project_brief=None, output_type="text", context_scope=None,
        temperature=0.7, max_output_tokens=4096, max_steps=8, models=(model,),
        advisor_model=None, utility_model=None, tool_levels={}, mcp_servers=(),
        capabilities=(), recall_enabled=True,
    )


def _row(i: int, **kw) -> HistoryRow:
    base = dict(
        id=f"h{i}", sender_type="human", sender_name="Noaman", content=f"message {i}",
        render_as="text", output_type="text", stopped=False, sequence=i, status=None,
    )
    base.update(kw)
    return HistoryRow(**base)


def test_t13_history_rules():
    """T13 — Every history rule, one row each, order kept.
    FAILED/CANCELLED/PENDING/STREAMING dropped; stopped dropped; system rows
    dropped; empty dropped; claims-HTML-but-isn't dropped; real HTML kept;
    visual-rendered-as-text dropped; another persona's reply prefixed
    [Another Agent: …]; the persona's own rows untouched; order never changes."""
    rows = [
        _row(1),                                                            # kept: user
        _row(2, status="FAILED", sender_type="persona", sender_name="NeuralBot"),     # dropped: status
        _row(3, status="CANCELLED"),                                        # dropped: status
        _row(4, status="PENDING"),                                          # dropped: status
        _row(5, status="STREAMING"),                                        # dropped: status
        _row(6, status="COMPLETED", sender_type="persona", sender_name="NeuralBot",
             content="my own earlier answer"),                              # kept: assistant, own
        _row(7, stopped=True, sender_type="persona", sender_name="NeuralBot"),        # dropped: stopped
        _row(8, sender_type="system", content="Session closed."),           # dropped: system
        _row(9, content="   "),                                             # dropped: empty
        _row(10, sender_type="persona", sender_name="NeuralBot",
             render_as="html", content="broken half render"),               # dropped: claims html, isn't
        _row(11, sender_type="persona", sender_name="NeuralBot",
             render_as="html", content="<html><body>ok</body></html>"),     # kept: real html
        _row(12, sender_type="persona", sender_name="NeuralBot",
             output_type="chart", render_as="text", content="chart fell back"),  # dropped: visual as text
        _row(13, sender_type="persona", sender_name="OtherBot",
             content="another agent's answer"),                             # kept, prefixed
        _row(14, content="latest question"),                                # kept: user
    ]
    selected = HistoryPolicy(depth=10).select(rows, _persona())

    assert [m.text for m in selected] == [
        "message 1",
        "my own earlier answer",
        "<html><body>ok</body></html>",
        "[Another Agent: OtherBot]\nanother agent's answer",
        "latest question",
    ]
    assert [m.role for m in selected] == ["user", "assistant", "assistant", "assistant", "user"]


def test_t13_status_none_is_kept():
    """T13 — A row from today's nucleus (no status field) is kept.
    The status filter only bites once nucleus change (2) lands; until then
    rows pass — 0.8.0 behaviour, so the module works against today's nucleus."""
    selected = HistoryPolicy(depth=10).select([_row(1, status=None)], _persona())
    assert len(selected) == 1


def test_t13_depth_caps_keeping_newest_in_order():
    """T13 — HISTORY_DEPTH caps the window: newest rows win, order kept (O3).
    14 valid rows with depth 10 → exactly the newest 10, oldest first, never
    reordered."""
    rows = [_row(i) for i in range(1, 15)]  # 14 valid user rows
    selected = HistoryPolicy(depth=10).select(rows, _persona())
    assert len(selected) == 10
    assert selected[0].text == "message 5" and selected[-1].text == "message 14"
