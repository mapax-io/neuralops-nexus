"""
Step 6 (docs/NUCLEUS-REVAMP.md) — the gateway's five tools.

Every tool runs AS a real person: the MCP endpoint resolved a user (personal
token, or internal key + user id) before anything here runs, and each tool
enforces the SAME visibility and rights the app's own endpoints use — the
gateway is a thin front door over existing roads, never new business logic
(owner's rule, handoff change 13.1).

An invisible thing answers like a nonexistent one, same as the app.
"""
from __future__ import annotations

import asyncio
import logging

from asgiref.sync import sync_to_async
from django.conf import settings

logger = logging.getLogger(__name__)

SEARCH_LIMIT = 8


class GatewayToolError(Exception):
    """A refused tool call; the message goes back to the MCP client verbatim."""


def _company():
    from workspace.services import get_company

    company = get_company()
    if not company:
        raise GatewayToolError("This server is not set up yet.")
    return company


def _find_topic(user, topic_id: str):
    """(company, project, topic) — the same row visibility chat uses."""
    from nucleus.models import ChatTopic
    from workspace import services as ws_svc
    from workspace.api import ws_visible_topic

    company = _company()
    try:
        topic = ChatTopic.objects.filter(id=topic_id, is_active=True).select_related("project").first()
    except Exception:  # noqa: BLE001 — a malformed id is just "no such topic"
        topic = None
    if not topic:
        raise GatewayToolError("No such topic.")
    project = ws_svc.get_project(company, user, str(topic.project_id))
    if not project or not ws_visible_topic(user, project, topic_id):
        raise GatewayToolError("No such topic.")
    return company, project, topic


# ── the five tools ──────────────────────────────────────────────────────────

async def list_projects(user) -> list[dict]:
    def _run():
        from workspace import services as ws_svc

        company = _company()
        return [
            {"id": str(p.id), "name": p.name, "description": p.description or ""}
            for p in ws_svc.list_projects(company, user)
        ]
    return await sync_to_async(_run)()


async def list_topics(user, project_id: str) -> list[dict]:
    def _run():
        from workspace import services as ws_svc

        company = _company()
        project = ws_svc.get_project(company, user, project_id)
        if not project:
            raise GatewayToolError("No such project.")
        out = []
        for channel in ws_svc.list_channels(user, project):
            for topic in ws_svc.list_topics(user, channel):
                out.append({
                    "id": str(topic.id), "title": topic.title,
                    "channel": channel.name, "project_id": str(project.id),
                })
        return out
    return await sync_to_async(_run)()


async def post_message(user, topic_id: str, content: str) -> dict:
    """A plain human message — no AI reply (ask_persona is the trigger road)."""
    from chat import services as chat_svc

    content = (content or "").strip()
    if not content:
        raise GatewayToolError("content is empty.")
    company, project, topic = await sync_to_async(_find_topic)(user, topic_id)
    msg = await sync_to_async(chat_svc.save_user_message)(
        company=company, project=project, topic=topic, user=user, content=content,
    )
    asyncio.create_task(chat_svc.publish_async(chat_svc.topic_channel(topic_id), msg))
    return {"ok": True, "message_id": msg["id"], "topic_id": topic_id}


async def ask_persona(user, topic_id: str, persona_name: str, message: str) -> dict:
    """
    Ask one of the project's personas and WAIT for the reply — the same trigger
    road chat uses (rights, reindex fence, queue-per-topic, relay). Past the
    timeout the reply keeps running and the answer says where to read it.
    """
    from authn.permissions.checker import PermissionChecker
    from chat import services as chat_svc
    from intelligence import services as intel_svc

    message = (message or "").strip()
    if not message:
        raise GatewayToolError("message is empty.")
    company, project, topic = await sync_to_async(_find_topic)(user, topic_id)

    if not await sync_to_async(PermissionChecker.can)(user, "persona.mention", obj=topic):
        raise GatewayToolError("You can't call personas in this topic.")
    if getattr(project, "reindex_status", "") == "building":
        raise GatewayToolError(
            "This project's memory is being rebuilt right now; try again once it finishes.")
    persona = await sync_to_async(intel_svc.get_persona_by_mention)(project, persona_name)
    if not persona or not persona.model_id:
        raise GatewayToolError(f"No persona named {persona_name!r} in this project.")

    msg = await sync_to_async(chat_svc.save_user_message)(
        company=company, project=project, topic=topic, user=user,
        content=f"@{persona.name} {message}",
    )
    asyncio.create_task(chat_svc.publish_async(chat_svc.topic_channel(topic_id), msg))

    run = asyncio.create_task(chat_svc.trigger_ai_response_async(
        company=company, project=project, topic=topic, persona=persona,
        user_message=message, user_message_id=msg["id"], topic_id=topic_id,
        output_type="auto", routine=None, triggered_by=user,
    ))
    timeout = int(getattr(settings, "GATEWAY_ASK_TIMEOUT_SECONDS", 180))
    done, _pending = await asyncio.wait({run}, timeout=timeout)
    if not done:
        # NOT cancelled — the relay finishes the reply into the topic.
        return {"status": "working", "topic_id": topic_id,
                "note": f"{persona.name} is still working — the reply will land in the topic."}

    reply = await sync_to_async(_newest_reply)(topic_id, str(persona.id), msg["sequence"])
    if not reply:
        return {"status": "unknown", "topic_id": topic_id,
                "note": "The run ended but no reply row was found — check the topic."}
    return reply


def _newest_reply(topic_id: str, persona_id: str, after_sequence: int) -> dict | None:
    from nucleus.models import ChatMessage

    row = (
        ChatMessage.objects
        .filter(topic_id=topic_id, sequence__gt=after_sequence, metadata__persona_id=persona_id)
        .order_by("-sequence")
        .first()
    )
    if not row:
        return None
    out = {
        "status": row.status,
        "message_id": str(row.id),
        "topic_id": topic_id,
        "persona": (row.metadata or {}).get("persona_name") or "",
        "content": row.content or "",
    }
    if row.status == ChatMessage.Status.PAUSED:
        out["note"] = ("The persona paused for an approval or a question — "
                       "answer it in the app; the reply then continues.")
    elif row.status == ChatMessage.Status.FAILED:
        out["note"] = "The reply failed — the content carries what the reader would see."
    return out


async def search_memory(user, query: str, project_id: str | None = None) -> list[dict]:
    """The same two-half search chat uses (W19): the engine ranks by meaning,
    nucleus filters by what THIS person may see; literal fallback when the
    engine can't answer."""
    from chat import search as search_svc
    from workspace import services as ws_svc

    query = (query or "").strip()
    if not query:
        raise GatewayToolError("query is empty.")

    def _scope():
        company = _company()
        if project_id:
            project = ws_svc.get_project(company, user, project_id)
            if not project:
                raise GatewayToolError("No such project.")
            projects = [str(project.id)]
        else:
            projects = [str(p.id) for p in ws_svc.list_projects(company, user)]
        return company, projects, search_svc.visible_topic_ids(user, company)

    company, project_ids, topic_ids = await sync_to_async(_scope)()
    if not topic_ids:
        return []
    try:
        ranked = await search_svc.semantic_ids(
            company, query[:search_svc.QUERY_MAX], project_ids, SEARCH_LIMIT)
    except Exception:  # noqa: BLE001 — search never fails the tool call
        ranked = []
    if ranked:
        rows = await sync_to_async(lambda: list(search_svc._rows(ranked, topic_ids)))()
        ordered = search_svc.order_by(ranked, rows)
    else:
        ordered = await sync_to_async(search_svc.literal)(query, topic_ids, SEARCH_LIMIT)
    return [search_svc._result(m, query) for m in ordered[:SEARCH_LIMIT]]
