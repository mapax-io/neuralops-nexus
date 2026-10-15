"""
Directive parsing — every @token a chat message can carry, in one place
(Step 2 split, docs/NUCLEUS-REVAMP.md; moved verbatim from chat/services.py
except /swarm, which is deleted — the swarm road is gone, owner's ruling 1).

chat/api.py:send_message() reads MessageDirectives' fields to decide what to
do; it never parses text itself.
"""
from __future__ import annotations

import re

# ── Known output type keywords ────────────────────────────────────────────────
# Must match the types registered in the engine (ai_engine output types).
_OUTPUT_TYPE_KEYWORDS = frozenset({
    "text", "code", "html", "chart", "table", "diagram", "form", "terminal",
})

# Matches @keyword where keyword is a known output type (case-insensitive)
_OUTPUT_TYPE_RE = re.compile(
    r"@(" + "|".join(_OUTPUT_TYPE_KEYWORDS) + r")\b",
    re.IGNORECASE,
)

# ── @session reserved keyword ─────────────────────────────────────────────────

# Matches "@session", "@session close", or "@session end" (case-insensitive)
_SESSION_RE = re.compile(r'@session(?:\s+(?:close|end))?\b', re.IGNORECASE)
_SESSION_CLOSE_RE = re.compile(r'@session\s+(?:close|end)\b', re.IGNORECASE)

# ── @mentions ─────────────────────────────────────────────────────────────────

# Matches @Word — finds ALL @mentions in a message.
_MENTION_RE = re.compile(r'@([\w]+)')

# Reserved keywords that are never persona names — everything else this
# module already parses as its own directive (@session/@session close,
# plus every output-type keyword above).
_RESERVED_MENTIONS = frozenset({"session", "close"}) | _OUTPUT_TYPE_KEYWORDS


def extract_session_directive(message: str) -> tuple[bool, bool, str]:
    """
    Detect @session / @session close / @session end in the user message.

    Returns:
        (has_session_open, is_close, clean_message)

        has_session_open — True if "@session" present (but not a close variant)
        is_close         — True if "@session close" or "@session end" present
        clean_message    — message with the @session directive stripped

    Examples:
        "@NeuralOps explain this @session"
            → (True, False, "@NeuralOps explain this")
        "@session close" or "@session end"
            → (False, True, "")
        "what is the weather"
            → (False, False, "what is the weather")
    """
    is_close = bool(_SESSION_CLOSE_RE.search(message))
    has_session = bool(_SESSION_RE.search(message)) and not is_close

    # Strip ALL @session / @session close occurrences from message
    clean = _SESSION_RE.sub("", message).strip()
    return has_session, is_close, clean


def extract_output_type(message: str) -> tuple[str, str]:
    """
    Detect @output_type directives in the user message.

    Returns:
        (output_type, clean_message)

    If no directive found, returns ("auto", original_message).
    If found, the directive is stripped from the message before it's sent to the AI.

    Examples:
        "Show me sales @chart for Q4"
            → ("chart", "Show me sales  for Q4")
        "@Nova explain the code @code"
            → ("code", "@Nova explain the code ")
        "@Nova explain the code"
            → ("auto", "@Nova explain the code")
    """
    m = _OUTPUT_TYPE_RE.search(message)
    if not m:
        return "auto", message

    output_type = m.group(1).lower()
    # Strip the @directive from the message text sent to the LLM
    clean = message[:m.start()] + message[m.end():]
    return output_type, clean.strip()


# A routine token: the FIRST standalone /name (lowercase letters, digits,
# hyphens) -- "/etc/hosts" and "50/50" are not. This finds a CANDIDATE only.
# Whether it IS a routine is a question for the project: "read the file at
# /tmp" and "compare /q3" are ordinary sentences, and treating every such
# token as a routine stripped it out of the message and refused the persona
# outright (audit, 2026-09-21).
_ROUTINE_RE = re.compile(r"(?:(?<=\s)|^)/([a-z0-9-]+)(?=\s|$)")


def extract_routine(message: str) -> tuple[str | None, str]:
    """(routine name, message without that token) -- one token, the first; the rest of the text is untouched."""
    m = _ROUTINE_RE.search(message)
    if not m:
        return None, message
    before, after = message[: m.start()], message[m.end():]
    # Only the token and one of the spaces around it go; the rest of the text stays as typed.
    if before.endswith(" ") and after.startswith(" "):
        after = after[1:]
    return m.group(1), (before + after).strip()


class MessageDirectives:
    """
    Every @directive a chat message can contain, parsed once, in one
    place. chat/api.py:send_message() reads the fields below to decide
    what to do -- it never parses text itself.

    Directives, checked/stripped in this order:
        @session            -- open a session with whoever gets @mentioned
        @session close/end  -- close the active session, no AI trigger
        @output_type        -- e.g. @chart, @html -- how the AI should
                                format its reply
        /routine-name       -- the first standalone /token (W4 Routines);
                                resolved against the topic's project by
                                send_message
        @PersonaName         -- one or more persona mentions (anything
                                left over that isn't a reserved keyword)

    (/swarm existed here until Step 2 of the revamp; the swarm road is
    deleted — a /swarm token is now just text.)

    Usage:
        directives = MessageDirectives(payload.content.strip())
        if directives.is_session_close:
            ...
        elif directives.has_mentions and directives.has_session_open:
            ...
    """

    def __init__(self, raw: str):
        self.raw = raw

        self.has_session_open, self.is_session_close, after_session = extract_session_directive(raw)
        self.output_type, self.clean_message = extract_output_type(after_session)
        # /routine-name -- resolved by send_message in the topic's project. The
        # token stays in clean_message until it resolves; message_without_routine
        # is the text to use once it has.
        self.routine_name, self.message_without_routine = extract_routine(self.clean_message)

        names = _MENTION_RE.findall(self.clean_message)
        self.mention_names = [n for n in names if n.lower() not in _RESERVED_MENTIONS]

    @property
    def has_mentions(self) -> bool:
        return bool(self.mention_names)

    def message_without_mentions(self, text: str | None = None) -> str:
        """`text` (default clean_message) with every @mention stripped too -- used
        to check whether there's any actual content left to send to the AI once
        the @PersonaName addressing is removed. send_message passes the text it
        settled on, which has the routine token out of it only if it was one."""
        return _MENTION_RE.sub("", self.clean_message if text is None else text).strip()
