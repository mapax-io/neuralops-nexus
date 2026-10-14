"""
chunk_text — paragraph packing for document ingestion (item 24 design §3).

Paragraphs are packed into ~CHUNK_CHARS pieces with a one-paragraph overlap so
a thought split across a boundary is still findable. A single paragraph longer
than the budget is split hard — never dropped.
"""
from __future__ import annotations

CHUNK_CHARS = 1000


def chunk_text(text: str, chunk_chars: int = CHUNK_CHARS) -> list[str]:
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        stripped = text.strip()
        return [stripped] if stripped else []
    # hard-split any paragraph that alone exceeds the budget
    pieces: list[str] = []
    for paragraph in paragraphs:
        while len(paragraph) > chunk_chars:
            pieces.append(paragraph[:chunk_chars])
            paragraph = paragraph[chunk_chars:]
        if paragraph:
            pieces.append(paragraph)
    chunks: list[str] = []
    current: list[str] = []
    size = 0
    for piece in pieces:
        if current and size + len(piece) > chunk_chars:
            chunks.append("\n\n".join(current))
            current = [current[-1]]  # one-paragraph overlap
            size = len(current[0])
        current.append(piece)
        size += len(piece)
    if current:
        chunks.append("\n\n".join(current))
    return chunks
