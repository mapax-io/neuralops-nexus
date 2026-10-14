"""
The output instruction as the model sees it (0.8.0's with_output_instruction,
ported from NA/managers/prompt_builder.py:55-80): the resolved type's
system_instruction plus the one standing exception — a choice prompt when the
persona must ask — for every type but a plan or a choice itself.

In the rebuild this becomes its own PromptSection (kind="output_format",
priority 85, unstable — the type can change per message), appended to the
plan the same way the retrieval section is; the generator joins sections with
blank lines, reproducing 0.8.0's composed prompt.
"""
from __future__ import annotations

from ai_engine.output_types.registry import TYPES_WITHOUT_CHOICE

CHOICE_EXCEPTION = (
    "One exception to the format above: when you genuinely cannot continue without the person choosing "
    "between a few concrete options (not a rhetorical question, not something you could decide or look up "
    "yourself), answer with ONLY a choice prompt, in exactly this form and nothing else:\n"
    "<<<OUTPUT:choice>>>\n"
    '{ "question": "one clear question", "options": [ { "id": "short-id", "label": "the option", "hint": "one line of consequence, optional" } ], "multiple": false }\n'
    "<<<END_OUTPUT>>>\n"
    "Two to six options; multiple is true only when more than one may be picked together. "
    "The person's pick comes back as their next message, and you carry on from there."
)


def output_instruction_block(system_instruction: str | None) -> str | None:
    """The section text for the resolved type, 0.8.0's shape kept."""
    if not system_instruction:
        return None
    block = system_instruction
    if not any(f"<<<OUTPUT:{name}>>>" in system_instruction for name in TYPES_WITHOUT_CHOICE):
        block = f"{system_instruction}\n\n{CHOICE_EXCEPTION}"
    return f"--- OUTPUT FORMAT INSTRUCTION ---\n{block}"
