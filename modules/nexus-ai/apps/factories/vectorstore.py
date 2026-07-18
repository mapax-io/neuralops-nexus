"""
VectorStoreFactory — returns the right VectorStore based on config.
"""
from apps.interfaces.vectorstore import VectorStore
from apps.core.config import settings


class VectorStoreFactory:
    @staticmethod
    def get(backend: str | None = None) -> VectorStore:
        backend = backend or settings.VECTOR_STORE

        match backend:
            case "chroma":
                from apps.implementations.vectorstore.chroma_store import ChromaStore
                return ChromaStore(
                    host=settings.CHROMA_HOST,
                    port=settings.CHROMA_PORT,
                )

            case "qdrant":
                from apps.implementations.vectorstore.qdrant_store import QdrantStore
                return QdrantStore()

            case "pgvector":
                from apps.implementations.vectorstore.pgvector_store import PgVectorStore
                return PgVectorStore()

            case _:
                raise ValueError(f"Unknown vector store: {backend!r}")
