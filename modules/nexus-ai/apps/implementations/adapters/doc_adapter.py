"""
Doc adapter — extracts and chunks text from documents.
Supports plain text and markdown. PDF support added when needed.
"""
from __future__ import annotations

import re
from apps.interfaces.adapter import ContextAdapter


class DocAdapter(ContextAdapter):
    """
    Chunks documents by paragraph.
    Empty lines separate paragraphs. Keeps chunks between 100–1000 chars.
    """

    MIN_CHUNK = 100
    MAX_CHUNK = 1000

    async def extract(
        self,
        content: str,
        metadata: dict | None = None,
    ) -> list[str]:
        # Split by blank lines (paragraph boundaries)
        raw_paragraphs = re.split(r"\n\s*\n", content.strip())

        chunks: list[str] = []
        buffer = ""

        for para in raw_paragraphs:
            para = para.strip()
            if not para:
                continue

            if len(buffer) + len(para) < self.MAX_CHUNK:
                buffer = f"{buffer}\n\n{para}".strip()
            else:
                if len(buffer) >= self.MIN_CHUNK:
                    chunks.append(buffer)
                buffer = para

        if len(buffer) >= self.MIN_CHUNK:
            chunks.append(buffer)

        return chunks or [content[:self.MAX_CHUNK]]
