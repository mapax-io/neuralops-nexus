"""
Output marker parsing.

Two marker formats are supported:

1. AI-generated markers (output type system instructions):
    <<<OUTPUT:typename>>>
    ... content ...
    <<<END_OUTPUT>>>

    <<<EMBED>>>
    Plain-text embed description (for ChromaDB).
    <<<END_EMBED>>>

2. MCP tool markers (returned by nexus-mcp tools):
    <<<HTML>>>  ... <<<END>>>
    <<<TERMINAL>>> ... <<<END>>>
    <<<FORM>>>  ... <<<END>>>
    <<<CONTEXT>>> ... <<<END>>>   ← natural-language narrative for embedding

MCP tool markers override AI-generated markers when both are present.
<<<CONTEXT>>> is always stripped from clean_content and returned as embed_description.
"""

from __future__ import annotations

import re

# ── AI-generated markers ───────────────────────────────────────────────────────

_OUTPUT_RE = re.compile(
    r"<<<OUTPUT:(\w+)>>>\s*(.*?)\s*<<<END_OUTPUT>>>",
    re.DOTALL,
)

_EMBED_RE = re.compile(
    r"<<<EMBED>>>\s*(.*?)\s*<<<END_EMBED>>>",
    re.DOTALL,
)

# ── MCP tool markers ───────────────────────────────────────────────────────────

_MCP_HTML_RE = re.compile(
    r"<<<HTML>>>\s*(.*?)\s*<<<END>>>",
    re.DOTALL,
)

_MCP_TERMINAL_RE = re.compile(
    r"<<<TERMINAL>>>\s*(.*?)\s*<<<END>>>",
    re.DOTALL,
)

_MCP_FORM_RE = re.compile(
    r"<<<FORM>>>\s*(.*?)\s*<<<END>>>",
    re.DOTALL,
)

_MCP_CONTEXT_RE = re.compile(
    r"<<<CONTEXT>>>\s*(.*?)\s*<<<END>>>",
    re.DOTALL,
)


def parse_output_markers(raw: str) -> tuple[str, str, str | None]:
    """
    Parse output type markers and optional embed description from an AI response.

    Returns:
        (clean_content, detected_type_name | None, embed_description | None)

    - clean_content:        response with ALL markers stripped
    - detected_type_name:   "html" | "terminal" | "form" | "code" | "chart" | ...
    - embed_description:    narrative text for ChromaDB embedding, or None

    Priority:
        MCP markers (<<<HTML>>> etc.) override AI-generated markers (<<<OUTPUT:>>>)
        <<<CONTEXT>>> is always used as embed_description when present
    """
    text = raw

    # ── Step 1: extract <<<CONTEXT>>> → embed_description ─────────────────────
    embed_description: str | None = None
    context_m = _MCP_CONTEXT_RE.search(text)
    if context_m:
        embed_description = context_m.group(1).strip()
        text = text[: context_m.start()] + text[context_m.end() :]

    # ── Step 2: extract <<<EMBED>>> (AI-generated, lower priority than CONTEXT)
    if not embed_description:
        embed_m = _EMBED_RE.search(text)
        if embed_m:
            embed_description = embed_m.group(1).strip()
            text = text[: embed_m.start()] + text[embed_m.end() :]

    # ── Step 3: detect MCP markers ────────────────────────────────────────────
    html_m = _MCP_HTML_RE.search(text)
    if html_m:
        clean = html_m.group(1).strip()
        # Strip remaining MCP markers (terminal/form won't co-exist, but be safe)
        clean = _MCP_TERMINAL_RE.sub("", clean)
        clean = _MCP_FORM_RE.sub("", clean)
        return clean, "html", embed_description

    terminal_m = _MCP_TERMINAL_RE.search(text)
    if terminal_m:
        clean = terminal_m.group(1).strip()
        return clean, "terminal", embed_description

    form_m = _MCP_FORM_RE.search(text)
    if form_m:
        clean = form_m.group(1).strip()
        return clean, "form", embed_description

    # ── Step 4: detect AI-generated markers ───────────────────────────────────
    output_m = _OUTPUT_RE.search(text)
    if output_m:
        clean = output_m.group(2).strip()
        type_name = output_m.group(1).strip().lower()
        return clean, type_name, embed_description

    # ── Step 5: plain text — no markers found ─────────────────────────────────
    return text.strip(), "text", embed_description
