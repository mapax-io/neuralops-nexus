"""
ai_engine/output_types — item 23 (Layer 4), ported from 0.8.0's
apps/output_types (all six files read and quoted in docs/NEXUS-AI-REVAMP.md's
Layer 4 verification notes).

What a reply LOOKS like: ten registered types; resolution is explicit
(non-auto from the trigger) → cosine-centroid classifier → "text"; the chosen
type's system_instruction is injected as its own prompt section; the finished
text is parsed for markers, recovered when the model dropped them, VALIDATED
(decision 2: a claimed type that doesn't hold falls back to text), and
message_done carries {content clean, output_type, render_as, embed_description}.

Importing this package registers the built-in types (legacy convention kept).
"""
from ai_engine.output_types import types as _types  # noqa: F401 — registration
from ai_engine.output_types.registry import OutputTypeRegistry, OutputTypeSpec, TYPES_WITHOUT_CHOICE
from ai_engine.output_types.resolver import resolve_output_spec
from ai_engine.output_types.recovery import finalise_reply

__all__ = ["OutputTypeRegistry", "OutputTypeSpec", "TYPES_WITHOUT_CHOICE",
           "resolve_output_spec", "finalise_reply"]
