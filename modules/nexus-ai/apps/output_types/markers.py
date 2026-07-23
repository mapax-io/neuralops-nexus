"""
Output marker parsing.

AI responses may contain:
    <<<OUTPUT:typename>>>
    ... content ...
    <<<END_OUTPUT>>>

This module extracts the typed content and strips the markers.
"""
from __future__ import annotations

import re

_MARKER_RE = re.compile(
    r"<<<OUTPUT:(\w+)>>>\s*(.*?)\s*<<<END_OUTPUT>>>",
    re.DOTALL,
)


def parse_output_markers(raw: str) -> tuple[str, str | None]:
    """
    Parse output type markers from an AI response.

    Returns:
        (clean_content, detected_type_name | None)

    If no markers are found, returns (raw, None).
    If markers are found, returns (content_inside_markers, type_name).
    """
    m = _MARKER_RE.search(raw)
    if not m:
        return raw, None
    return m.group(2).strip(), m.group(1).strip().lower()
