"""
PromptTemplates — renders the Jinja2 template files that live beside this module.
"""
from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

DEFAULT_TEMPLATE_DIR = Path(__file__).parent / "templates"


class PromptTemplates:
    def __init__(self, template_dir: Path = DEFAULT_TEMPLATE_DIR) -> None:
        self._env = Environment(
            loader=FileSystemLoader(str(template_dir)),
            undefined=StrictUndefined,
            keep_trailing_newline=False,
            autoescape=False,
        )

    def render(self, name: str, values: dict) -> str:
        return self._env.get_template(name).render(**values)
