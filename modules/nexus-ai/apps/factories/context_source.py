"""
ContextSourceFactory — returns the right ContextSource plugin by type.

To add a new context type:
    1. Create implementations/context_sources/{type}/ module
    2. Implement ContextSource interface
    3. Add one case here

The rest of the system never changes.
"""
from apps.interfaces.context_source import ContextSource
from apps.factories.embedding import EmbeddingFactory
from apps.factories.vectorstore import VectorStoreFactory


class ContextSourceFactory:
    @staticmethod
    def get(source_type: str) -> ContextSource:
        embedder = EmbeddingFactory.get()
        store = VectorStoreFactory.get()

        match source_type:
            case "document" | "doc" | "code":
                from apps.implementations.context_sources.document.document_context_source import DocumentContextSource
                return DocumentContextSource(embedder=embedder, store=store)

            case "chat":
                from apps.implementations.context_sources.chat.chat_context_source import ChatContextSource
                return ChatContextSource(embedder=embedder, store=store)

            case _:
                raise ValueError(
                    f"Unknown context source type: {source_type!r}. "
                    f"Valid options: 'document', 'doc', 'code', 'chat'"
                )
