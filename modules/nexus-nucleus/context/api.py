"""
Context API — attach / detach / list ContextSources for a topic.

Mounted under /projects/ in authn/urls.py, so full paths are:
    GET    /api/v1/projects/{project_id}/topics/{topic_id}/context-sources/
    POST   /api/v1/projects/{project_id}/topics/{topic_id}/context-sources/file/
    POST   /api/v1/projects/{project_id}/topics/{topic_id}/context-sources/web/
    DELETE /api/v1/projects/{project_id}/topics/{topic_id}/context-sources/{source_id}/

M6 additions:
    GET    /api/v1/projects/{project_id}/topics/{topic_id}/context-panel/
    DELETE /api/v1/projects/{project_id}/topics/{topic_id}/context-panel/items/
"""
import logging
from typing import List

from ninja import Router, File
from ninja.files import UploadedFile

from authn.auth import SupabaseBearer
from .schema import ContextSourceOut, ContextSourceWebIn, PanelDeleteIn
from . import services as svc
from . import panel_providers as _panel_providers  # noqa: F401 — registers all providers on import
from .panel_provider import ContextPanelRegistry
from chat.services import save_system_message, publish, topic_channel

router = Router(tags=["Context"], auth=SupabaseBearer())

logger = logging.getLogger(__name__)


def _company(request):
    from nucleus.models import Company
    return Company.objects.filter(is_active=True).first()


def _topic(project_id: str, topic_id: str):
    from nucleus.models import ChatTopic
    return ChatTopic.objects.select_related("channel__project").get(
        id=topic_id,
        project_id=project_id,
        is_active=True,
    )


def _out(source) -> ContextSourceOut:
    return ContextSourceOut(
        id=str(source.id),
        topic_id=str(source.topic_id),
        type=source.type,
        name=source.name,
        url=source.url,
        collection_id=source.collection_id,
        status=source.status,
        error=source.error,
        created_at=source.created_at.isoformat(),
    )


# ── Directives ───────────────────────────────────────────────────────────────

@router.get("/context-sources/directives/", response=List[dict])
def list_directives(request):
    """Proxy to nexus-ai — returns all registered @directives with help text."""
    import httpx
    from django.conf import settings
    nexus_ai_url = getattr(settings, "NEXUS_AI_URL", "")
    internal_key = getattr(settings, "INTERNAL_API_KEY", "")
    try:
        resp = httpx.get(
            f"{nexus_ai_url}/api/v1/directives/",
            headers={"X-Internal-Key": internal_key},
            timeout=5,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return []


# ── List ──────────────────────────────────────────────────────────────────────

@router.get("/{project_id}/topics/{topic_id}/context-sources/", response=List[ContextSourceOut])
def list_context_sources(request, project_id: str, topic_id: str):
    sources = svc.list_context_sources(topic_id)
    return [_out(s) for s in sources]


# ── Attach file ───────────────────────────────────────────────────────────────

@router.post("/{project_id}/topics/{topic_id}/context-sources/file/", response={201: ContextSourceOut})
def attach_file(
    request,
    project_id: str,
    topic_id: str,
    file: UploadedFile = File(...),
):
    company = _company(request)
    topic = _topic(project_id, topic_id)
    source = svc.attach_file(company=company, topic=topic, uploaded_file=file)

    user = request.auth
    user_name = user.get_display_name() if user else "Someone"

    if source.status == "ready":
        content = f"{user_name} added {source.name} to context"
    else:
        content = f"{user_name} tried to add {source.name} to context (failed to embed)"

    sys_msg = save_system_message(
        company=company,
        project=topic.project,
        topic=topic,
        content=content,
    )
    publish(topic_channel(topic_id), sys_msg)

    return 201, _out(source)


# ── Attach web URL ────────────────────────────────────────────────────────────

@router.post("/{project_id}/topics/{topic_id}/context-sources/web/", response={201: ContextSourceOut})
def attach_web(
    request,
    project_id: str,
    topic_id: str,
    payload: ContextSourceWebIn,
):
    company = _company(request)
    topic = _topic(project_id, topic_id)
    source = svc.attach_web(
        company=company,
        topic=topic,
        url=payload.url,
        name=payload.name,
    )
    return 201, _out(source)


# ── Detach (legacy single-source endpoint) ────────────────────────────────────

@router.delete("/{project_id}/topics/{topic_id}/context-sources/{source_id}/", response={200: dict})
def detach_context_source(request, project_id: str, topic_id: str, source_id: str):
    from nucleus.models import ContextSource
    try:
        source = ContextSource.objects.get(id=source_id, is_active=True)
        source_name = source.name
    except ContextSource.DoesNotExist:
        return 404, {"error": "Context source not found"}

    found = svc.detach_context_source(source_id)
    if not found:
        return 404, {"error": "Context source not found"}

    company = _company(request)
    topic = _topic(project_id, topic_id)
    user = request.auth
    user_name = user.get_display_name() if user else "Someone"
    sys_msg = save_system_message(
        company=company,
        project=topic.project,
        topic=topic,
        content=f"{user_name} removed {source_name} from context",
    )
    publish(topic_channel(topic_id), sys_msg)

    return 200, {"ok": True}


# ── Context Panel — GET ───────────────────────────────────────────────────────

@router.get("/{project_id}/topics/{topic_id}/context-panel/", response=List[dict])
def get_context_panel(request, project_id: str, topic_id: str):
    """
    Return the full context panel tree for a topic.

    Each entry is a group (e.g. "Files", "Chat History") with its items nested
    inside.  The frontend renders this tree generically — no hard-coded knowledge
    of specific context source types is needed in the UI.
    """
    company = _company(request)
    topic = _topic(project_id, topic_id)
    result = []
    for provider in ContextPanelRegistry.get_all():
        try:
            result.append(provider.to_dict(topic, company))
        except Exception as exc:
            logger.warning(
                "[panel] provider '%s' failed to build dict: %s",
                provider.directive, exc,
            )
    return result


# ── Context Panel — DELETE items ──────────────────────────────────────────────

@router.delete("/{project_id}/topics/{topic_id}/context-panel/items/", response={200: dict})
def delete_panel_items(request, project_id: str, topic_id: str, payload: PanelDeleteIn):
    """
    Remove selected items from context.

    Each item in the payload specifies a directive (e.g. "file", "chat") and
    the item id.  The matching provider handles the deletion logic:
      - file: detaches the ContextSource record + ChromaDB collection
      - chat: sets is_deleted_from_context=True on the ChatMessage
    """
    company = _company(request)
    topic = _topic(project_id, topic_id)
    user = request.auth
    user_name = user.get_display_name() if user else "Someone"

    deleted: list[str] = []

    for item in payload.items:
        try:
            provider = ContextPanelRegistry.get(item.directive)
        except KeyError:
            logger.warning("[panel] unknown directive '%s' in delete request", item.directive)
            continue

        # For file items: capture the label before deleting (for system message)
        item_label: str | None = None
        if item.directive == "file":
            from nucleus.models import ContextSource
            try:
                src = ContextSource.objects.get(id=item.id, is_active=True)
                item_label = src.name
            except ContextSource.DoesNotExist:
                pass

        try:
            provider.delete_item(item.id, topic, company)
            deleted.append(item.id)
        except Exception as exc:
            logger.warning(
                "[panel] delete_item failed for %s:%s — %s",
                item.directive, item.id, exc,
            )
            continue

        # Publish system messages for file removals only
        # (chat message exclusions would be too noisy to broadcast)
        if item_label:
            sys_msg = save_system_message(
                company=company,
                project=topic.project,
                topic=topic,
                content=f"{user_name} removed {item_label} from context",
            )
            publish(topic_channel(topic_id), sys_msg)

    return 200, {"ok": True, "deleted": deleted}
