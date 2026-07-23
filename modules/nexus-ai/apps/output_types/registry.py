"""
OutputType registry — maps output type names to their specs.

Each spec declares:
  name                 — unique key used in @mentions and markers ("chart", "code", ...)
  render_as            — the frontend renderer to use ("html" | "code" | "text" | "terminal")
  label                — human-readable label for UI
  icon                 — lucide-react icon name
  system_instruction   — injected into the system prompt to guide the AI
  example_prompts      — used by the cosine similarity classifier to detect intent
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class OutputTypeSpec:
    name: str
    render_as: str                         # "text" | "code" | "html" | "terminal"
    label: str
    icon: str
    system_instruction: str
    example_prompts: list[str] = field(default_factory=list)


class _OutputTypeRegistry:
    def __init__(self) -> None:
        self._types: dict[str, OutputTypeSpec] = {}

    def register(self, spec: OutputTypeSpec) -> None:
        self._types[spec.name] = spec

    def get(self, name: str) -> OutputTypeSpec | None:
        return self._types.get(name)

    def all(self) -> list[OutputTypeSpec]:
        return list(self._types.values())

    def names(self) -> list[str]:
        return list(self._types.keys())


OutputTypeRegistry = _OutputTypeRegistry()
