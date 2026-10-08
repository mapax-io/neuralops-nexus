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


def mention_refused_event(msg_id: str, actor_user_id: str, refusals: list[dict]) -> dict:
    """
    For the sender only: the personas in their message that will not answer,
    and why. It rides the topic channel like everything else -- clients drop
    it unless actor_user_id is their own -- so the sender's other tabs learn it
    too. `id` is the HUMAN message the note attaches to.
    """
    return {"type": "mention_refused", "id": msg_id, "actor_user_id": actor_user_id, "refusals": refusals}


def tool_activity_end_event(msg_id: str, event: dict) -> dict | None:
    """
    The tool_activity_end payload for a worker tool_call_end event: how the
    call went, so the client can close the row tool_activity opened. None
    when the event names no tool.
    """
    result = event.get("tool_result") or {}
    name = (result.get("name") or "").strip()
    if not name:
        return None
    return {
        "type": "tool_activity_end",
        "id": msg_id,
        "tool": name,
        "ok": bool(result.get("ok")),
        "duration_ms": int(result.get("duration_ms") or 0),
        "preview": result.get("preview"),
        "error": result.get("error"),
        "url": result.get("url"),
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


def tool_approval_event(msg_id: str, approval: dict) -> dict:
    """A tool call the worker holds for a person: the record as the row now holds it (pending)."""
    return {"type": "tool_approval", "id": msg_id, "approval": approval}


def tool_approval_decided_event(msg_id: str, approval: dict) -> dict:
    """A person allowed or denied a held call: the record with who decided what."""
    return {"type": "tool_approval_decided", "id": msg_id, "approval": approval}


def preflight_decided_event(msg_id: str, preflight: dict) -> dict:
    """A person decided a proposal: the whole preflight record, as the row now holds it."""
    return {"type": "preflight_decided", "id": msg_id, "preflight": preflight}
