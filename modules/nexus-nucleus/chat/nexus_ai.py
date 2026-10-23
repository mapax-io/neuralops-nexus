"""
NexusAIClient — the one class that talks to the engine (Step 2, owner's
ruling 4: "there must be some client here for nexus-ai... that should be
clear"). Nothing else in nucleus reads NEXUS_AI_URL or opens a connection
to the engine; raw httpx calls to it anywhere else are a bug.

What the engine offers (its fastapi_app):
  POST /api/v1/trigger/        — a reply, streamed back as SSE AgentEvents.
                                 A RESUME is the same endpoint: the original
                                 job fields plus a `resume` block.
  POST /api/v1/embed/message/  — fire-and-forget message embedding.
  POST /api/v1/embed/          — document embedding (returns collection_id).
  DELETE /api/v1/embed/…       — drop vectors (source / message).
  POST /api/v1/embed/reindex/  — rebuild a project's vectors (Step 3 — the
                                 embedder changed); GET …/status/ to poll.

The async methods serve the relay; the SYNC methods below serve ordinary
Django views and Celery tasks (context uploads, the reindex task).

The stream honours a should_stop callable (the reader's Stop button) both
while waiting for the first byte and between lines — closing the stream
cancels the engine's generator and its model call.
"""
from __future__ import annotations

import json
import logging
from typing import AsyncIterator, Awaitable, Callable

import httpx
from django.conf import settings

from .stop_signals import stoppable, stoppable_lines

logger = logging.getLogger(__name__)

TRIGGER_TIMEOUT = 120


class NexusAIClient:
    """Every call to nexus-ai, in one place."""

    def __init__(self, base_url: str | None = None, internal_key: str | None = None):
        self.base_url = (base_url if base_url is not None else getattr(settings, "NEXUS_AI_URL", "")).rstrip("/")
        self.internal_key = internal_key if internal_key is not None else getattr(settings, "INTERNAL_API_KEY", "")

    @property
    def configured(self) -> bool:
        return bool(self.base_url)

    @property
    def _headers(self) -> dict:
        return {"X-Internal-Key": self.internal_key, "Content-Type": "application/json"}

    async def stream_trigger(
        self, job: dict, should_stop: Callable[[], Awaitable[bool]],
    ) -> AsyncIterator[dict]:
        """
        POST the trigger job and yield each SSE event as a parsed dict.
        A resume is the same call — `job` simply carries the resume block.
        Raises RuntimeError on a non-200, StopRequested when should_stop says
        so (the connection closes, which cancels the engine's run).
        """
        async with httpx.AsyncClient(timeout=TRIGGER_TIMEOUT) as client:
            request = client.build_request(
                "POST", f"{self.base_url}/api/v1/trigger/",
                json=job, headers=self._headers,
            )
            # The engine does its own setup before the first byte comes back;
            # a Stop must land during that wait too, not only once lines flow.
            response = await stoppable(client.send(request, stream=True), should_stop)
            try:
                if response.status_code != 200:
                    body = await response.aread()
                    raise RuntimeError(
                        f"nexus-ai /trigger/ returned {response.status_code}: {body.decode()[:300]}"
                    )
                async for line in stoppable_lines(response.aiter_lines(), should_stop):
                    if not line.startswith("data: "):
                        continue
                    raw = line[6:].strip()
                    if not raw:
                        continue
                    try:
                        yield json.loads(raw)
                    except (json.JSONDecodeError, TypeError):
                        continue
            finally:
                await response.aclose()

    async def embed_message(self, payload: dict) -> None:
        """
        Fire-and-forget: send message data to nexus-ai for embedding.
        Errors are logged and swallowed — embedding failure must never
        affect chat.
        """
        if not self.configured:
            logger.warning("[embed] NEXUS_AI_URL not set — skipping message embedding")
            return
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/api/v1/embed/message/",
                    json=payload, headers=self._headers, timeout=15,
                )
                if response.status_code != 200:
                    logger.warning(
                        "[embed] nexus-ai returned %s for message %s",
                        response.status_code, payload.get("message_id"),
                    )
        except Exception as exc:  # noqa: BLE001
            logger.warning("[embed] embed_message failed message=%s: %s", payload.get("message_id"), exc)

    # ── sync side (views + Celery) ───────────────────────────────────────

    def embed_document(self, payload: dict) -> str:
        """POST /embed/ — chunk + store a context source. Returns the
        collection_id ('{project_id}:{source_id}'). Raises on failure — the
        caller marks the source ERROR."""
        if not self.configured:
            raise RuntimeError("NEXUS_AI_URL not configured")
        resp = httpx.post(f"{self.base_url}/api/v1/embed/", json=payload,
                          headers=self._headers, timeout=60)
        resp.raise_for_status()
        return resp.json()["collection_id"]

    def delete_context_source(self, collection_id: str) -> None:
        """DELETE /embed/context-source/{collection_id}/ — logged, never raises."""
        if not self.configured:
            return
        try:
            httpx.delete(f"{self.base_url}/api/v1/embed/context-source/{collection_id}/",
                         headers=self._headers, timeout=10)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[embed] failed to delete collection %s: %s", collection_id, exc)

    # REMOVED (2026-10-22): embed_recall / delete_recall_vector — Recall left
    # the product with migration 0042.

    def delete_message_vector(self, message_id: str, company_id: str, project_id: str | None = None) -> None:
        """DELETE /embed/message/{id}/ — drops the vector AND the reply's tool
        memory (same id); logged, never raises."""
        if not self.configured:
            return
        params = {"company_id": company_id}
        if project_id:
            params["project_id"] = project_id  # skips the engine's company scan
        try:
            httpx.delete(f"{self.base_url}/api/v1/embed/message/{message_id}/",
                         headers=self._headers, params=params, timeout=10)
        except Exception as exc:  # noqa: BLE001
            logger.debug("[embed] message vector delete failed for %s: %s", message_id, exc)

    def start_reindex(self, company_id: str, project_id: str, embedder: dict) -> tuple[bool, str]:
        """POST /embed/reindex/ — (True, 'building') on 202; (False, detail) on
        409 (one already building) or any other failure."""
        if not self.configured:
            return False, "NEXUS_AI_URL not configured"
        try:
            resp = httpx.post(f"{self.base_url}/api/v1/embed/reindex/",
                              json={"company_id": company_id, "project_id": project_id, "embedder": embedder},
                              headers=self._headers, timeout=30)
            if resp.status_code == 202:
                return True, "building"
            return False, resp.json().get("detail", f"status {resp.status_code}")
        except Exception as exc:  # noqa: BLE001
            return False, f"{type(exc).__name__}: {exc}"

    def reindex_status(self, project_id: str) -> dict:
        """GET /embed/reindex/{project_id}/status/ — {status, done, total}; raises on failure."""
        resp = httpx.get(f"{self.base_url}/api/v1/embed/reindex/{project_id}/status/",
                         headers=self._headers, timeout=15)
        resp.raise_for_status()
        return resp.json()

    def list_mcp_tools(self, url: str, bearer_token: str | None = None) -> tuple[bool, list | str]:
        """POST /mcp/tools/ (Step 6, change 6) — the engine dials an MCP server
        and lists its tools [{name, one_line, read_only}]. (True, tools) or
        (False, reason) — the reason is shown verbatim next to the Refresh
        button, never raised."""
        if not self.configured:
            return False, "NEXUS_AI_URL not configured"
        try:
            resp = httpx.post(f"{self.base_url}/api/v1/mcp/tools/",
                              json={"url": url, "bearer_token": bearer_token},
                              headers=self._headers, timeout=30)
            if resp.status_code == 200:
                return True, resp.json().get("tools", [])
            return False, resp.json().get("detail", f"status {resp.status_code}")
        except Exception as exc:  # noqa: BLE001
            return False, f"{type(exc).__name__}: {exc}"
