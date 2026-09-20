"""
One place that decides which output type a run uses.

Priority: the explicit type nucleus sends for an @chart-style directive, then
cosine classification of the message, then "text".

Callers get the SPEC, not just the name -- the spec carries the
`system_instruction` the model must be given (the <<<OUTPUT:...>>> contract)
and the `render_as` the frontend needs. Handing a caller only the name is how
the model ended up being told "chart" and nothing else.
"""
from __future__ import annotations

import logging

from .registry import OutputTypeRegistry, OutputTypeSpec

logger = logging.getLogger(__name__)

DEFAULT_TYPE = "text"


async def resolve_output_spec(job) -> tuple[str, OutputTypeSpec | None]:
    """Return (type_name, spec) for this job. `job` is a TriggerJob or TriggerSwarmJob."""
    name = await _resolve_name(job)
    spec = OutputTypeRegistry.get(name)

    if spec is None:
        spec = OutputTypeRegistry.get(DEFAULT_TYPE)
        name = spec.name if spec else DEFAULT_TYPE

    return name, spec


async def _resolve_name(job) -> str:
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

    try:
        detected = await classifier.classify_output_type(job.message)
        logger.debug("[output-type] classified: %s", detected)
        return detected
    except Exception as exc:
        logger.warning("[output-type] classifier failed: %s", exc)
        return DEFAULT_TYPE
