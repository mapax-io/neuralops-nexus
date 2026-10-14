"""
ReembedJob — embedder change ⇒ FULL re-embed (Layer 3 decisions 4 + 8).

Runs inside nexus-ai (vectors are nexus-ai's property): nucleus locks the
project, POSTs /embed/reindex/, and polls the status endpoint. The walk reads
the OLD schema's stored raw text — nothing is re-fetched — and the flip is
atomic in the registry: searches answer OLD vectors until the new set is
complete, so a crash mid-rebuild loses nothing.
"""
from __future__ import annotations

import logging

from ai_engine.vector_db.txtai_store import TxtaiVectorStore

log = logging.getLogger(__name__)


class ReembedJob:
    def __init__(self, store: TxtaiVectorStore) -> None:
        self._store = store

    def start(self, company_id: str, project_id: str, embedder_spec: dict) -> dict:
        """Registers the BUILDING index or raises VectorStoreBusy (→ 409)."""
        return self._store.start_reindex(company_id, project_id, embedder_spec)

    def run(self, project_id: str) -> None:
        """The blocking walk — call from a background thread."""
        try:
            self._store.run_reindex(project_id)
        except Exception:  # noqa: BLE001 — the status endpoint shows the stall
            log.exception("reindex failed for project %s — old index stays active",
                          project_id)

    def status(self, project_id: str) -> dict:
        return self._store.reindex_status(project_id)
