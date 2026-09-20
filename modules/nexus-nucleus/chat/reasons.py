"""
Why a persona reply failed, in a sentence the reader can act on.

Raw error text never leaves the server: it can carry API keys, hostnames and
stack frames. It stays in metadata.error_detail. What reaches the bubble is a
category, chosen by matching the raw text, and the category's sentence.
"""
from __future__ import annotations

import re

GENERIC_REASON = "Something went wrong generating this response."
ORPHANED_RUN_REASON = "The server restarted while this reply was being generated. Nothing was lost — mention the persona again."
WORKER_ENDED_EARLY_REASON = "The AI worker stopped replying before it finished. Mention the persona again to retry."

# Order matters: the first pattern that matches wins.
_CATEGORIES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"invalid_api_key|incorrect api key|authentication_error|\b401\b|unauthori[sz]ed", re.I),
     "The model provider rejected this model's API key. Check the key on the AI models page."),
    (re.compile(r"insufficient_quota|\b402\b|billing|no remaining|exceeded your current quota", re.I),
     "The model provider reports no remaining credit for this model's key."),
    (re.compile(r"rate.?limit|\b429\b|too many requests", re.I),
     "The model provider rate-limited this request. Try again in a moment."),
    (re.compile(r"model_not_found|does not exist|\b404\b.*model|unknown model", re.I),
     "The model provider does not know this model id. Check the model on the AI models page."),
    (re.compile(r"context.?length|maximum context|too many tokens|token limit", re.I),
     "The conversation is longer than this model can take in. Start a new chat or use a larger model."),
    (re.compile(r"peer closed|connection (reset|refused|closed|attempts failed)|remoteprotocolerror|readerror|unreachable|econnrefused|incomplete message body", re.I),
     "The AI worker closed the connection or could not be reached."),
    (re.compile(r"content.?filter|safety|blocked by|\brefusal\b|refused to", re.I),
     "The model provider declined to answer this request."),
    (re.compile(r"mcp|call_tool|tool", re.I),
     "A tool the persona uses failed. Check its MCP server on the MCP page."),
    (re.compile(r"timed? ?out|timeout|deadline", re.I),
     "The AI worker took too long to answer and the request timed out."),
    (re.compile(r"stopped replying|ended (the )?stream|before it finished", re.I),
     WORKER_ENDED_EARLY_REASON),
    (re.compile(r"\b5\d\d\b|internal server error|bad gateway|service unavailable", re.I),
     "The model provider returned a server error. Try again in a moment."),
    # Our own bug, not the provider's: say so, so it gets reported instead of retried.
    (re.compile(r"(NameError|TypeError|AttributeError|KeyError|ValueError|IndexError|ImportError|AssertionError|is not defined|has no attribute|object is not)", re.I),
     "NeuralOps hit an internal error while handling this reply. This is a bug on our side — please report it."),
]


def explain_ai_error(raw: str | None) -> str:
    text = raw or ""
    for pattern, sentence in _CATEGORIES:
        if pattern.search(text):
            return sentence
    return GENERIC_REASON
