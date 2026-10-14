"""
VectorStore — the interface the rest of nexus-ai talks to (Layer 3 decision 1).

One index per PROJECT, each in its own pg schema (decision 7 + trial C rule i);
the implementation is TxtaiVectorStore. Framework-free file: the shapes live in
core/specs.py, txtai appears only in txtai_store.py.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Sequence

from ai_engine.core.specs import SearchHit, SearchQuery, VectorItem


class VectorStoreBusy(Exception):
    """A reindex is already building for this project (design: one at a time →
    the endpoint answers 409)."""


class VectorStore(ABC):
    @abstractmethod
    def index(self, company_id: str, project_id: str,
              items: Sequence[VectorItem],
              embedder_spec: dict | None = None) -> str:
        """Upsert rows into the project's ACTIVE index, creating it on first
        use (with embedder_spec, or the system default). Returns the active
        embedder's model_id."""

    @abstractmethod
    def search(self, query: SearchQuery) -> list[SearchHit]:
        """Hybrid search over the project's active index, scoped by the
        query's filters. An absent index answers [] — 'db is empty for it'."""

    @abstractmethod
    def delete_source(self, company_id: str, project_id: str, source: str) -> int:
        """Drop every row whose source matches. Returns how many went."""

    @abstractmethod
    def delete_ids(self, company_id: str, project_id: str,
                   ids: Sequence[str]) -> int:
        """Drop specific rows (message delete, recall delete)."""

    @abstractmethod
    def active_model(self, project_id: str) -> str | None:
        """The model_id of the project's active index, or None when the
        project has no index yet."""

    @abstractmethod
    def has_index(self, project_id: str) -> bool:
        """True when the project has an ACTIVE index (retrieval's gate)."""

    @abstractmethod
    def active_schema(self, project_id: str) -> str | None:
        """The active index's schema name — the legacy `collection` field."""

    @abstractmethod
    def projects_for_company(self, company_id: str) -> list[str]:
        """Project ids with an active index for this company — the legacy
        message/recall deletes carry only company_id, so they scan these."""
