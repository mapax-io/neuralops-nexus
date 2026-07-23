"""
ContextSourceFactory — auto-registration via @ContextSourceFactory.register decorator.

Each ContextSource subclass declares:
    directive: str  — the @command users type ("file", "chat", "url", "code", ...)
    help: str       — one-line description shown in the status bar

To add a new context type:
    1. Create implementations/context_sources/{type}/ module
    2. Implement ContextSource — set directive + help
    3. Decorate with @ContextSourceFactory.register
    4. That's it — factory, directives endpoint, and status bar all auto-update
"""
from __future__ import annotations

from typing import Type

from apps.interfaces.context_source import ContextSource
from apps.factories.embedding import EmbeddingFactory
from apps.factories.vectorstore import VectorStoreFactory


class ContextSourceFactory:
    _registry: dict[str, Type[ContextSource]] = {}

    @classmethod
    def register(cls, source_class: Type[ContextSource]) -> Type[ContextSource]:
        """Decorator — register a ContextSource class by its directive."""
        if not source_class.directive:
            raise ValueError(f"{source_class.__name__} must define a directive")
        cls._registry[source_class.directive] = source_class
        return source_class

    @classmethod
    def get(cls, directive: str) -> ContextSource:
        """Return an initialised ContextSource plugin for the given directive."""
        if directive not in cls._registry:
            raise ValueError(
                f"Unknown context directive: {directive!r}. "
                f"Registered: {list(cls._registry)}"
            )
        embedder = EmbeddingFactory.get()
        store = VectorStoreFactory.get()
        return cls._registry[directive](embedder=embedder, store=store)

    @classmethod
    def get_all_directives(cls) -> list[dict]:
        """Return all registered directives with their help text — for the status bar."""
        return [
            {"directive": directive, "help": klass.help}
            for directive, klass in cls._registry.items()
        ]


# ── Register all built-in plugins ────────────────────────────────────────────
# Import triggers the decorator, which registers the class.
# Order here determines order in get_all_directives() output.

from apps.implementations.context_sources.chat.chat_context_source import ChatContextSource          # noqa: E402
from apps.implementations.context_sources.document.document_context_source import DocumentContextSource  # noqa: E402

ContextSourceFactory.register(ChatContextSource)
ContextSourceFactory.register(DocumentContextSource)
