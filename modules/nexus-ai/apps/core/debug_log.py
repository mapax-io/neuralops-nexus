"""
Optional per-request debug file.

When AI_REQUEST_DEBUG_LOG names a path, every model call appends one JSON
line there: who triggered it, which persona and model served it, the full
prompt as sent, the response and the usage. That is the only place the
prompt and response go -- nucleus keeps counts, never text (decision 6 of
the usage plan). Off by default; meant for a developer's own stack.
"""
import json
import logging
import os
import threading

from apps.core.config import settings

log = logging.getLogger(__name__)
_lock = threading.Lock()
MAX_BYTES = 50 * 1024 * 1024  # roll to <path>.1 past this, keep one generation


def dump_messages(messages) -> list:
    """The prompt as plain data -- pydantic-ai messages if that is what they are."""
    try:
        from pydantic_ai.messages import ModelMessagesTypeAdapter
        return ModelMessagesTypeAdapter.dump_python(list(messages), mode="json")
    except Exception:  # noqa: BLE001 -- a builder may hand over plain dicts
        return [m if isinstance(m, dict) else str(m) for m in messages]


def write_ai_request_debug(record: dict) -> None:
    path = settings.AI_REQUEST_DEBUG_LOG
    if not path:
        return
    line = json.dumps(record, default=str) + "\n"
    with _lock:
        try:
            if os.path.exists(path) and os.path.getsize(path) > MAX_BYTES:
                os.replace(path, path + ".1")
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(line)
        except OSError as exc:
            log.warning("[debug-log] could not write %s: %s", path, exc)
