"""
Recover a reply whose model followed the output contract but dropped the
<<<OUTPUT:...>>> markers around it.

Without markers parse_output_markers reads the reply as plain text, and the app
shows a chart description as a paragraph of JSON. The description is still a
chart; when a chart was what the run resolved to, and the whole reply is one
JSON object shaped like a description, report it as the chart it is.

Strict on purpose: the entire reply must be the object -- prose around it means
the model was talking, not charting -- and only the resolved type is recovered,
never a type the classifier did not pick.
"""
from __future__ import annotations

import json
import re

# A lone marker -- the model opened without closing, or closed without opening.
_STRAY_MARKERS = re.compile(r"<{2,3}(?:OUTPUT:\w+|END_OUTPUT|EMBED|END_EMBED)>{0,3}")

RECOVERABLE = {"chart": ("type", "datasets")}


def recover_unmarked(resolved_type: str, content: str) -> str | None:
    required = RECOVERABLE.get(resolved_type)
    if not required:
        return None
    text = _STRAY_MARKERS.sub("", content).strip()
    if not (text.startswith("{") and text.endswith("}")):
        return None
    try:
        value = json.loads(text)
    except ValueError:
        return None
    if not isinstance(value, dict):
        return None
    # one description, or a reply of several: {"charts": [description, ...]}
    candidates = value.get("charts") if "charts" in value else [value]
    if not isinstance(candidates, list) or not candidates:
        return None
    if not all(isinstance(c, dict) and all(key in c for key in required) for c in candidates):
        return None
    return resolved_type


def strip_stray_markers(content: str) -> str:
    return _STRAY_MARKERS.sub("", content).strip()


def finalise_reply(raw: str, resolved_type: str) -> tuple[str, str, str, str | None]:
    """
    What a finished reply is: (clean content, output type, render_as, embed
    description). Markers name the type; without them the reply is text --
    the model answered conversationally -- unless it is the unmarked chart
    the run asked for. The single and the swarm path both end here.
    """
    from apps.output_types import OutputTypeRegistry
    from apps.output_types.markers import parse_output_markers

    clean, marker_type, embed_description = parse_output_markers(raw)
    spec = OutputTypeRegistry.get(marker_type)
    # parse_output_markers reports "text" when it found no markers at all.
    if spec is None or spec.name == "text":
        recovered = recover_unmarked(resolved_type, clean)
        if recovered:
            spec = OutputTypeRegistry.get(recovered)
            clean = strip_stray_markers(clean)
    final_type = spec.name if spec else "text"
    render_as = getattr(spec, "render_as", None) or "text"
    return clean, final_type, render_as, (None if render_as == "text" else embed_description)
