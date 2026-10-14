"""
ask_user — item 5 (Layer 4): the model asks the person a question and WAITS.

Trial H's road: a kind='external' tool never executes in-process — calling it
ends the run with DeferredToolRequests.calls (the same pause shape as item 2's
approvals), the state goes to nucleus, and the person's ANSWER comes back on
the resume as the tool result (DeferredToolResults.calls). One road for
approvals, discovery and questions.

The toolset is added only on INTERACTIVE, question-capable runs (the plain
reply and the deep/standard runs): an unattended run has nobody to answer, and
the router's screening run hints rather than acts — neither gets the tool, so
neither can stall on it. 0.8.0 had only a prompt convention here
(NA/managers/prompt_builder.py:55-78); the real tool replaces it.
"""
from __future__ import annotations

from pydantic_ai.tools import ToolDefinition
from pydantic_ai.toolsets import ExternalToolset

ASK_USER_NAME = "ask_user"
ASK_USER_CAPABILITY_ID = "ask-user"

_ASK_USER = ToolDefinition(
    name=ASK_USER_NAME,
    description=(
        "Ask the person a question and wait for their answer. Use it ONLY when "
        "you genuinely cannot continue without their input — never for "
        "rhetorical questions or things you could decide or look up yourself. "
        "Their answer arrives as this tool's result."
    ),
    parameters_json_schema={
        "type": "object",
        "properties": {
            "question": {"type": "string", "description": "One clear question."},
            "options": {
                "type": "array", "items": {"type": "string"},
                "description": "Two to six concrete options, when the answer is a pick.",
            },
        },
        "required": ["question"],
    },
    kind="external",
)


def ask_user_toolset() -> ExternalToolset:
    return ExternalToolset([_ASK_USER], id=ASK_USER_CAPABILITY_ID)
