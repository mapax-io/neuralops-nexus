"""
ai_engine/vector_db — the ONLY folder that touches txtai, pgvector, and
sqlalchemy-for-vectors (docs/NEXUS-AI-REVAMP.md §1.3 Layer 3 decision 1, the
same quarantine rule that confines pydantic-ai to pydantic_ai_system/).

Everything is reached through the interfaces in store.py / embedder.py; txtai
itself imports lazily inside txtai_store.py (it pulls torch — a process that
never uses vectors never pays that import).
"""
from ai_engine.vector_db.embedder import Embedder, EmbedderFactory
from ai_engine.vector_db.store import VectorStore, VectorStoreBusy

_store = None
_store_url: str | None = None


def get_store() -> VectorStore | None:
    """THE process's one store (see TxtaiVectorStore.close: a second handle on
    the same schemas deadlocks on the first one's locks). None = the feature
    is off (NEXUS_VECTOR_DB_URL unset) — retrieval skips, endpoints 503."""
    global _store, _store_url
    from ai_engine.core.config import EngineSettings
    settings = EngineSettings()
    if not settings.vector_db_url:
        return None
    if _store is None or _store_url != settings.vector_db_url:
        from ai_engine.vector_db.txtai_store import TxtaiVectorStore
        _store = TxtaiVectorStore(settings.vector_db_url, settings.vector_config_dir)
        _store_url = settings.vector_db_url
    return _store


__all__ = ["Embedder", "EmbedderFactory", "VectorStore", "VectorStoreBusy", "get_store"]
