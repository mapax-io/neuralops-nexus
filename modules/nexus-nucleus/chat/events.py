"""
chat/events.py

The realtime contract: what nucleus publishes on a topic-{id} Centrifugo
channel, as plain data and payload builders. No ORM, no business decisions --
services.py decides WHEN to publish, this decides WHAT the payload looks like.

Same split as authn/permissions/rights.py (the registry) vs checker.py (the
logic), and the mirror of the web app's lib/realtime/events.ts, which parses
exactly these shapes.

Deliberately NOT in chat/schema.py: that file is the HTTP contract (Ninja
request/response models for the REST endpoints). Publish payloads are a
different contract with a different consumer, and mixing them makes it unclear
which shapes a route can return.
"""

# Readable phrasing for the tool a persona is using, published with
# tool_activity so the client renders what the server says rather than keeping
# its own copy of the tool vocabulary -- a new built-in or a newly registered
# MCP tool then needs no frontend change.
#
# Built-ins come from DEFAULT_PROJECT_CAPABILITIES (workspace/services.py); the
# rest are the swarm control tools the agentic loop calls on itself.
TOOL_ACTIVITY_LABELS = {
    "web_search": "Searching the web",
    "web_fetch": "Reading a page",
    "shell": "Running a command",
    "filesystem": "Reading files",
    "handoff_task": "Handing over",
    "delegate_task": "Delegating",
    "continue_work": "Still working",
}


def tool_activity_event(msg_id: str, event: dict) -> dict | None:
    """
    The tool_activity payload for a worker tool_call_start event, or None when
    the event carries no tool name (nothing useful to show, so publish nothing).

    Anything outside TOOL_ACTIVITY_LABELS -- an MCP server's own tool -- falls
    back to its name, de-underscored, so it still reads as a sentence.
    """
    call = event.get("tool_call") or {}
    name = (call.get("name") or "").strip()
    if not name:
        return None
    return {
        "type": "tool_activity",
        "id": msg_id,
        "tool": name,
        "label": TOOL_ACTIVITY_LABELS.get(name) or f"Using {name.replace('_', ' ')}",
    }
