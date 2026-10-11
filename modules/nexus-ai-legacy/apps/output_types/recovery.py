"""
Recover a reply whose model followed the output contract but dropped the
<<<OUTPUT:...>>> markers around it.

Without markers parse_output_markers reads the reply as plain text, and the app
shows a chart description as a paragraph of JSON. The description is still a
chart; when a chart was what the run resolved to, and the whole reply is one
JSON object shaped like a description, report it as the chart it is.

Strict on purpose: the entire reply must be the object -- prose around it means
the model was talking, not charting -- and only the resolved type is recovered,
never a type the classifier did not pick. The one type every ordinary turn may
answer with is a choice prompt (prompt_builder.CHOICE_EXCEPTION), so a reply
shaped like one is a choice whatever the turn resolved to -- except a preflight
turn, whose instruction never offered it.
"""
from __future__ import annotations

import json
import re

from .registry import TYPES_WITHOUT_CHOICE

# A lone marker -- the model opened without closing, or closed without opening.
_STRAY_MARKERS = re.compile(r"<{2,3}(?:OUTPUT:\w+|END_OUTPUT|EMBED|END_EMBED)>{0,3}")

RECOVERABLE = {"chart": ("type", "datasets"), "choice": ("question", "options")}


def _whole_object(content: str) -> dict | None:
    text = _STRAY_MARKERS.sub("", content).strip()
    if not (text.startswith("{") and text.endswith("}")):
        return None
    try:
        value = json.loads(text)
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


def _shaped_as(kind: str, value: dict) -> bool:
    required = RECOVERABLE[kind]
    if kind == "choice":
        return all(key in value for key in required) and isinstance(value["options"], list) and bool(value["options"])
    # one description, or a reply of several: {"charts": [description, ...]}
    candidates = value.get("charts") if "charts" in value else [value]
    if not isinstance(candidates, list) or not candidates:
        return False
    return all(isinstance(c, dict) and all(key in c for key in required) for c in candidates)


def recover_unmarked(resolved_type: str, content: str) -> str | None:
    value = _whole_object(content)
    if value is None:
        return None
    if resolved_type in RECOVERABLE and _shaped_as(resolved_type, value):
        return resolved_type
    if resolved_type not in TYPES_WITHOUT_CHOICE and _shaped_as("choice", value):
        return "choice"
    return None


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
