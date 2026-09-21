"""
Recall (W5): what the team's personas have recorded about a project --
decisions, facts, preferences -- short, attributed, and read into every
persona's turn in the project. Nucleus is the writer of record; the worker
keeps the vectors (collection company_{id}_recall, doc id = entry id) so a
run can retrieve what is relevant.

Dedupe is by normalised text within the project, enforced here rather than
by a database constraint so a removed entry can be recorded again.
"""
from __future__ import annotations

import logging
import re
import threading

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)

RECALL_KINDS = ("decision", "fact", "preference")
RECALL_TEXT_MAX = 500
# What one reply may add, and how much a project may hold.
RECALL_PER_RUN_MAX = 5
RECALL_PER_PROJECT_MAX = 500


def normalize(text: str) -> str:
    """The dedupe key: one case, one space, no trailing punctuation."""
    return re.sub(r"\s+", " ", (text or "").strip().lower()).rstrip(".!;,: ")


def validate_entry(kind: str, text: str) -> tuple[str, str]:
    kind = (kind or "").strip().lower()
    text = re.sub(r"\s+", " ", (text or "").strip())
    if kind not in RECALL_KINDS:
        raise ValueError("An entry is a decision, a fact or a preference.")
    if not text:
        raise ValueError("An entry needs some text.")
    if len(text) > RECALL_TEXT_MAX:
        raise ValueError("An entry is at most %d characters." % RECALL_TEXT_MAX)
    return kind, text


def list_recall(project, kind: str | None = None, q: str | None = None):
    from nucleus.models import RecallEntry
    rows = (
        RecallEntry.objects.filter(project=project, is_active=True)
        .select_related("author_persona", "source_topic", "source_topic__channel", "created_by")
        .order_by("-created_at")
    )
    if kind:
        rows = rows.filter(kind=kind)
    if q:
        rows = rows.filter(text__icontains=q.strip())
    return list(rows)


def get_recall_entry(project, entry_id: str):
    from nucleus.models import RecallEntry
    return RecallEntry.objects.filter(project=project, id=entry_id, is_active=True).select_related("author_persona", "source_topic", "source_topic__channel", "created_by").first()


def record_recall(project, entries: list[dict], *, persona=None, message=None, user=None) -> dict:
    """
    Store what a reply (or a person) recorded: validated, deduplicated against
    the project's active entries and within the batch, capped per run and by
    the project's ceiling. Returns {"created": [entries], "skipped": n}.
    Raises ValueError for an entry that is not valid at all.
    """
    from nucleus.models import RecallEntry
    cleaned = [validate_entry(e.get("kind"), e.get("text")) for e in entries or []]
    if not cleaned:
        return {"created": [], "skipped": 0}
    existing = set(RecallEntry.objects.filter(project=project, is_active=True).values_list("normalized", flat=True))
    room = max(0, RECALL_PER_PROJECT_MAX - len(existing))
    created: list = []
    skipped = 0
    for kind, text in cleaned:
        key = normalize(text)
        if key in existing or len(created) >= RECALL_PER_RUN_MAX or len(created) >= room:
            skipped += 1
            continue
        entry = RecallEntry.objects.create(
            company=project.company, project=project, kind=kind, text=text, normalized=key,
            author_persona=persona, source_message=message, source_topic=message.topic if message is not None else None,
            created_by=user,
        )
        existing.add(key)
        created.append(entry)
        embed_recall_entry(entry)
    return {"created": created, "skipped": skipped}


def patch_recall(project, entry_id: str, data: dict):
    """Edit an entry's text or kind; the vector follows. ValueError when the new text is already recorded."""
    entry = get_recall_entry(project, entry_id)
    if not entry:
        return None
    from nucleus.models import RecallEntry
    kind, text = validate_entry(data.get("kind") or entry.kind, data.get("text") if data.get("text") is not None else entry.text)
    key = normalize(text)
    if key != entry.normalized and RecallEntry.objects.filter(project=project, normalized=key, is_active=True).exclude(id=entry.id).exists():
        raise ValueError("The project already has an entry saying that.")
    entry.kind, entry.text, entry.normalized = kind, text, key
    entry.save(update_fields=["kind", "text", "normalized", "updated_at"])
    embed_recall_entry(entry)
    return entry


def delete_recall(project, entry_id: str) -> bool:
    entry = get_recall_entry(project, entry_id)
    if not entry:
        return False
    entry.soft_delete()
    delete_recall_vector(entry)
    return True


# ── the worker's vectors: best effort, never in the way ──────────────────────
def _worker() -> tuple[str, str]:
    return getattr(settings, "NEXUS_AI_URL", ""), getattr(settings, "INTERNAL_API_KEY", "")


def _later(fn, *args) -> None:
    """Run off the request: embedding waits on the worker's model, and the worker is the one calling us."""
    if getattr(settings, "RECALL_EMBED_INLINE", False):
        fn(*args)
        return
    threading.Thread(target=fn, args=args, daemon=True).start()


def embed_recall_entry(entry) -> None:
    _later(_embed_now, entry)


def delete_recall_vector(entry) -> None:
    _later(_delete_now, entry)


def _embed_now(entry) -> None:
    url, key = _worker()
    if not url:
        return
    try:
        httpx.post(
            f"{url}/api/v1/embed/recall/",
            json={
                "entry_id": str(entry.id), "company_id": str(entry.company_id), "project_id": str(entry.project_id),
                "kind": entry.kind, "text": entry.text,
                "author_name": entry.author_persona.name if entry.author_persona_id and entry.author_persona else None,
                "topic_id": str(entry.source_topic_id) if entry.source_topic_id else None,
                "created_at": entry.created_at.isoformat() if entry.created_at else None,
            },
            headers={"X-Internal-Key": key},
            timeout=15,
        ).raise_for_status()
    except Exception as exc:  # noqa: BLE001 -- a missing vector is a weaker recall, not a failed write
        logger.warning("[recall] embed failed for %s: %s", entry.id, type(exc).__name__)


def _delete_now(entry) -> None:
    url, key = _worker()
    if not url:
        return
    try:
        httpx.delete(f"{url}/api/v1/embed/recall/{entry.id}/", params={"company_id": str(entry.company_id)}, headers={"X-Internal-Key": key}, timeout=10)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[recall] vector delete failed for %s: %s", entry.id, type(exc).__name__)
