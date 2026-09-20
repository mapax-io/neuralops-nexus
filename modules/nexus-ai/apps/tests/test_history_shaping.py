"""
Which past messages the model is shown. Filtering happens here in the worker,
on rows nucleus hands over raw (internal/api.py get_topic_history_internal).
"""
from apps.managers.nucleus_client import shape_history


def row(**over):
    base = {"sender_type": "persona", "content": "done", "render_as": "text", "output_type": "text", "sender_name": "Sara"}
    return {**base, **over}


def test_a_reply_the_reader_stopped_is_left_out_of_history():
    history = shape_history([
        row(sender_type="human", content="chart please"),
        row(content='{"type": "bar", "title": "Sal', stopped=True),
        row(content="here it is", render_as="chart", output_type="chart"),
    ])
    assert [(m.role, m.content) for m in history] == [("user", "chart please"), ("assistant", "here it is")]


def test_history_keeps_the_existing_filters():
    history = shape_history([
        row(sender_type="system", content="Session closed."),
        row(content="", ),
        row(content="broken", render_as="html"),
        row(content="fell back", output_type="chart", render_as="text"),
        row(content="<!DOCTYPE html><html></html>", render_as="html", output_type="html"),
    ])
    assert [m.content for m in history] == ["<!DOCTYPE html><html></html>"]
