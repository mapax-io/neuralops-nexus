"""
Code adapter — chunks source code by function/class boundaries.
Phase 1: regex-based chunking for Python and common languages.
Phase 2: replace with tree-sitter AST parsing for all languages.
"""
from __future__ import annotations

import re
from apps.interfaces.adapter import ContextAdapter


# Patterns that mark the start of a new top-level definition
_DEFINITION_PATTERNS = [
    r"^(async\s+)?def\s+\w+",          # Python functions
    r"^class\s+\w+",                    # Python / JS classes
    r"^(export\s+)?(async\s+)?function\s+\w+",  # JS/TS functions
    r"^(export\s+)?const\s+\w+\s*=\s*(async\s+)?\(",  # JS/TS arrow functions
    r"^\s*(public|private|protected|static).*\w+\s*\(",  # Java/C# methods
]

_DEF_RE = re.compile("|".join(_DEFINITION_PATTERNS), re.MULTILINE)


class CodeAdapter(ContextAdapter):
    """
    Chunks code by function/class boundaries.
    Each chunk = one top-level definition.
    Falls back to fixed-size chunks for languages without detected boundaries.
    """

    MAX_CHUNK = 1500

    async def extract(
        self,
        content: str,
        metadata: dict | None = None,
    ) -> list[str]:
        chunks = self._split_by_definitions(content)

        if not chunks:
            # Fallback: split by fixed size with line boundaries
            chunks = self._split_fixed(content)

        return chunks

    def _split_by_definitions(self, content: str) -> list[str]:
        """Split at function/class definition boundaries."""
        matches = list(_DEF_RE.finditer(content))
        if not matches:
            return []

        chunks: list[str] = []
        for i, match in enumerate(matches):
            start = match.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
            chunk = content[start:end].strip()
            if chunk:
                # Split oversized chunks at line boundaries
                if len(chunk) > self.MAX_CHUNK:
                    chunks.extend(self._split_fixed(chunk))
                else:
                    chunks.append(chunk)

        return chunks

    def _split_fixed(self, content: str, size: int = 800) -> list[str]:
        """Split by fixed char count, breaking at newlines."""
        lines = content.splitlines(keepends=True)
        chunks: list[str] = []
        buffer = ""
        for line in lines:
            if len(buffer) + len(line) > size and buffer:
                chunks.append(buffer.strip())
                buffer = ""
            buffer += line
        if buffer.strip():
            chunks.append(buffer.strip())
        return chunks
