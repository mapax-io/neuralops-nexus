"""
One place that decides which output type a run uses.

Priority: the explicit type nucleus sends for an @chart-style directive, then
cosine classification of the message, then "text".

A pick -- the person's answer to a choice prompt, "@Faisal → Last 10 years" --
says nothing about the shape of the reply it unlocks, so it is classified from
the request that raised the question (the user message before the last choice
in history), never from its own words.

Callers get the SPEC, not just the name -- the spec carries the
`system_instruction` the model must be given (the <<<OUTPUT:...>>> contract)
and the `render_as` the frontend needs. Handing a caller only the name is how
the model ended up being told "chart" and nothing else.
"""
from __future__ import annotations

import logging
import re
from collections.abc import Sequence

from apps.schemas.trigger import HistoryMessage

from .registry import OutputTypeRegistry, OutputTypeSpec

logger = logging.getLogger(__name__)

DEFAULT_TYPE = "text"

# Mirrors the app's pickMessage (choice-card.tsx): an optional leading mention,
# then "→ " and the chosen labels.
_PICK = re.compile(r"^(?:@[\w-]+\s+)?→\s")


def request_behind_pick(message: str, history: Sequence[HistoryMessage]) -> str | None:
    """
    For a pick, the user message that led to the last choice prompt -- skipping
    earlier picks, since a chain of questions still answers one request. None
    when the message is not a pick or nothing in history asked for anything.
    """
    if not _PICK.match(message):
        return None
    rows = list(history)
    last_choice = next((i for i in range(len(rows) - 1, -1, -1) if rows[i].role == "assistant" and rows[i].output_type == "choice"), len(rows))
    for row in reversed(rows[:last_choice]):
        if row.role == "user" and not _PICK.match(row.content):
            return row.content
    return None


async def resolve_output_spec(job, history: Sequence[HistoryMessage] = ()) -> tuple[str, OutputTypeSpec | None]:
    """Return (type_name, spec) for this job. `job` is a TriggerJob or TriggerSwarmJob."""
    name = await _resolve_name(job, history)
    spec = OutputTypeRegistry.get(name)

    if spec is None:
        spec = OutputTypeRegistry.get(DEFAULT_TYPE)
        name = spec.name if spec else DEFAULT_TYPE

    return name, spec


async def _resolve_name(job, history: Sequence[HistoryMessage]) -> str:
    explicit = getattr(job, "output_type", None)

    if explicit and explicit != "auto":
        if OutputTypeRegistry.get(explicit):
            logger.debug("[output-type] explicit: %s", explicit)
            return explicit
        logger.warning(
            "[output-type] unknown explicit type %r — classifying instead", explicit
        )

    # Imported here, not at module scope: the classifier pulls in the embedder.
    from . import classifier

    request = request_behind_pick(job.message, history)
    if request is not None:
        logger.debug("[output-type] pick — classifying the request behind it")
    try:
        detected = await classifier.classify_output_type(request if request is not None else job.message)
        logger.debug("[output-type] classified: %s", detected)
        return detected
    except Exception as exc:
        logger.warning("[output-type] classifier failed: %s", exc)
        return DEFAULT_TYPE
