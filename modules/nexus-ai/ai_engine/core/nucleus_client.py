"""
NucleusClient — every call to nucleus goes through here (dependency rule 3).

Auth: sends BOTH header spellings for the internal key. Today's nucleus checks
X-Internal-API-Key; O5 unifies both directions on X-Internal-Key (nucleus
change 5). Sending both costs nothing and works against either nucleus.

get_persona maps PersonaInternal into PersonaSpec and applies nucleus change (3)
on this side until nucleus has model roles: persona.model → STANDARD,
fallback_models → FALLBACK in order.
"""
from __future__ import annotations

import logging
from dataclasses import asdict

import httpx

from ai_engine.core.specs import HistoryRow, ModelRole, ModelSpec, PauseInfo, PersonaSpec, UsageRecord

log = logging.getLogger(__name__)

USAGE_PATH = "/api/v1/internal/usage/"  # new endpoint — nucleus change (1)
# Item 2 / item 27 — nucleus change (9): store a paused run's state under its
# message; the resume trigger carries it back verbatim.
PAUSE_PATH = "/api/v1/internal/messages/{msg_id}/pause/"


class NucleusClient:
    def __init__(self, base_url: str, internal_key: str, timeout_seconds: float = 10.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._headers = {
            "X-Internal-Key": internal_key,       # O5 — the unified name
            "X-Internal-API-Key": internal_key,   # what today's nucleus checks
        }

    async def get_persona(self, persona_id: str, company_id: str, project_id: str) -> PersonaSpec:
        url = f"{self._base_url}/api/v1/internal/personas/{persona_id}/"
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.get(url, headers=self._headers)
            response.raise_for_status()
        return persona_from(response.json(), company_id=company_id, project_id=project_id)

    async def get_history(self, topic_id: str, limit: int, exclude_message_id: str) -> list[HistoryRow]:
        url = f"{self._base_url}/api/v1/internal/topics/{topic_id}/history/"
        params: dict = {"limit": limit}
        if exclude_message_id:
            params["exclude_message_id"] = exclude_message_id
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.get(url, params=params, headers=self._headers)
            response.raise_for_status()
        return [history_row_from(m) for m in response.json()]

    async def record_usage(self, records: list[UsageRecord]) -> None:
        """POST every record. The CALLER decides what a failure means — per the
        Layer 0 rules it is logged and never turns a good reply into an error."""
        if not records:
            return
        url = f"{self._base_url}{USAGE_PATH}"
        payload = {"records": [_usage_payload(r) for r in records]}
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(url, json=payload, headers=self._headers)
            response.raise_for_status()

    async def get_nudges(self, msg_id: str) -> list[str]:
        """W8 (Layer 4): what the caller typed while this reply runs — taken
        once (nucleus consumes on GET). Raises on failure; the NudgeGate treats
        any failure as 'no nudge'."""
        url = f"{self._base_url}/api/v1/internal/messages/{msg_id}/nudges/"
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.get(url, headers=self._headers)
            response.raise_for_status()
            return [t for t in (response.json().get("nudges") or [])
                    if isinstance(t, str) and t.strip()]

    async def save_pause(self, msg_id: str, job_id: str, topic_id: str,
                         persona_id: str, pause: PauseInfo, role: str = "STANDARD") -> None:
        """POST the paused run's state (item 2). MUST land before the stream's
        message_paused is sent, so a decision can never race an unsaved state.
        role (item 13): which model seat was running — the resume rebuilds on
        the same seat (ResumeBlock.role)."""
        url = f"{self._base_url}{PAUSE_PATH.format(msg_id=msg_id)}"
        payload = {
            "job_id": job_id,
            "topic_id": topic_id,
            "persona_id": persona_id,
            "state": pause.state,
            "catalog_hash": pause.catalog_hash,
            "pending": [asdict(p) for p in pause.pending],
            "role": role,
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(url, json=payload, headers=self._headers)
            response.raise_for_status()


# ── mapping ────────────────────────────────────────────────────────────────────


def model_spec_from(data: dict, role: ModelRole) -> ModelSpec:
    """ModelInternal → ModelSpec. context_window arrives from nucleus and is
    kept apart from the persona's output limit, always."""
    return ModelSpec(
        role=role,
        config_id=str(data["id"]),
        name=data.get("name") or data["model_id"],
        provider=data["provider"],
        model_id=data["model_id"],
        base_url=data.get("api_base"),
        api_key=data.get("api_key"),
        context_window=int(data["context_window"]),
        supports_tools=bool(data.get("supports_tools", True)),
        supports_streaming=bool(data.get("supports_streaming", True)),
        supports_vision=bool(data.get("supports_vision", False)),
    )


def persona_from(data: dict, company_id: str, project_id: str) -> PersonaSpec:
    """PersonaInternal → PersonaSpec. Every field nucleus sends has a place."""
    prompt = data.get("prompt") or {}
    models = [model_spec_from(data["model"], ModelRole.STANDARD)]
    # Item 13 (nucleus change 3, concrete shape): the optional ROUTER and DEEP
    # seats arrive as router_model / deep_model; absent = the seat is empty and
    # the behaviour falls back (no routing / no escalation target beyond STANDARD).
    if data.get("router_model"):
        models.append(model_spec_from(data["router_model"], ModelRole.ROUTER))
    if data.get("deep_model"):
        models.append(model_spec_from(data["deep_model"], ModelRole.DEEP))
    models += [model_spec_from(m, ModelRole.FALLBACK) for m in data.get("fallback_models") or []]
    advisor = data.get("advisor_model")
    utility = data.get("utility_model")
    return PersonaSpec(
        id=str(data["id"]),
        name=data["name"],
        company_id=company_id,
        project_id=project_id,
        system_prompt=prompt.get("system_prompt", ""),
        project_brief=data.get("project_brief"),
        output_type=prompt.get("output_type", "text"),
        context_scope=prompt.get("context_scope"),
        temperature=float(data.get("temperature", 0.7)),
        max_output_tokens=int(data.get("max_tokens", 4096)),
        max_steps=int(data.get("max_steps", 0)),
        models=tuple(models),
        advisor_model=model_spec_from(advisor, ModelRole.STANDARD) if advisor else None,
        utility_model=model_spec_from(utility, ModelRole.STANDARD) if utility else None,
        tool_levels=data.get("tool_levels") or {},
        mcp_servers=tuple(data.get("mcp_servers") or []),
        capabilities=tuple(data.get("capabilities") or []),
        recall_enabled=bool(data.get("recall_enabled", True)),
        tool_access=data.get("tool_access") or "selected",  # nucleus change (7); absent → selected
        approval_scope=data.get("approval_scope") or "topic",  # item 2 decision 5; absent → topic
    )


def history_row_from(data: dict) -> HistoryRow:
    return HistoryRow(
        id=str(data["id"]),
        sender_type=data.get("sender_type", "system"),
        sender_name=data.get("sender_name"),
        content=data.get("content") or "",
        render_as=data.get("render_as", "text"),
        output_type=data.get("output_type", "text"),
        stopped=bool(data.get("stopped")),
        sequence=int(data.get("sequence", 0)),
        status=data.get("status"),  # None from an older nucleus
    )


def _usage_payload(record: UsageRecord) -> dict:
    payload = asdict(record)
    payload["called_at"] = record.called_at.isoformat()
    payload["cost"] = str(record.cost) if record.cost is not None else None
    return payload
