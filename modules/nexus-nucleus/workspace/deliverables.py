"""
Deliverables (W10): what a persona produced and the team decided to keep.

A reply scrolls away. A chart someone signed off, a page a client saw, the
table a decision was made from — those want a name and a shelf. Keeping is by
TITLE: keeping the same title again adds a version rather than overwriting, so
last week's number is still there beside the one that replaced it.

Nothing is generated here and nothing is re-rendered: a deliverable holds
exactly the content the reply carried, so the app draws it with the same block
it already uses.
"""
import logging

from django.db import IntegrityError, transaction

logger = logging.getLogger(__name__)

TITLE_MAX = 120
CONTENT_MAX = 400_000
# One list request never pulls more than this -- the runbook runs list uses the
# same cap, and nothing in the app pages past it.
LIST_MAX = 200
# How many times a keep re-reads the next version when someone beat it to one.
KEEP_ATTEMPTS = 3
# What a reply can be kept as -- the renderers the app already has.
KEEPABLE = ("html", "chart", "table", "form", "text")


class DeliverableError(Exception):
    """A keep that cannot happen; `status` is the HTTP answer."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def list_deliverables(project, *, title: str | None = None, latest_only: bool = False, limit: int = LIST_MAX):
    """
    The kept things, newest version of each title first. Never their content:
    a list of 200 charts would otherwise pull every stored body out of Postgres
    only for summary() to drop it (audit, 2026-09-21).
    """
    from nucleus.models import Deliverable
    rows = Deliverable.objects.filter(project=project, is_active=True).defer("content").select_related("created_by")
    if title:
        rows = rows.filter(title=title)
    rows = list(rows.order_by("title", "-version")[: max(1, min(int(limit), LIST_MAX))])
    if latest_only:
        seen, latest = set(), []
        for row in rows:  # ordered newest version first within each title
            if row.title in seen:
                continue
            seen.add(row.title)
            latest.append(row)
        return latest
    return rows


def get_deliverable(project, deliverable_id: str):
    from nucleus.models import Deliverable
    return Deliverable.objects.filter(project=project, id=deliverable_id, is_active=True).select_related("created_by").first()


def next_version(project, title: str) -> int:
    """The version this title would be kept as next -- 1 the first time."""
    from django.db.models import Max
    from nucleus.models import Deliverable
    highest = (
        Deliverable.objects.filter(project=project, title=title, is_active=True)
        .aggregate(Max("version"))["version__max"]
    )
    return (highest or 0) + 1


def keep(company, project, user, *, title: str, kind: str, content: str, source_message=None):
    """
    Keep a reply's content under `title`. Returns the new Deliverable.

    A repeat of a title is a new version, never an overwrite: someone who linked
    v1 still has v1.
    """
    from nucleus.models import Deliverable

    title = (title or "").strip()
    if not title:
        raise DeliverableError(400, "Give it a name so the team can find it.")
    if len(title) > TITLE_MAX:
        raise DeliverableError(400, f"The name is at most {TITLE_MAX} characters.")
    if kind not in KEEPABLE:
        raise DeliverableError(400, "That is not something this app can keep.")
    if not (content or "").strip():
        raise DeliverableError(400, "There is nothing in that reply to keep.")
    if len(content) > CONTENT_MAX:
        raise DeliverableError(413, "That reply is too large to keep.")

    # next_version() reads and create() writes, and the unique constraint covers
    # (project, title, version) among live rows: two people keeping the same name
    # at once used to give the second an IntegrityError and a 500 (audit,
    # 2026-09-21). Each attempt is its own transaction so a failure does not
    # poison the caller's.
    row = None
    for _ in range(KEEP_ATTEMPTS):
        try:
            with transaction.atomic():
                row = Deliverable.objects.create(
                    company=company, project=project, created_by=user, source_message=source_message,
                    title=title, kind=kind, content=content, version=next_version(project, title),
                )
            break
        except IntegrityError:
            continue
    if row is None:
        raise DeliverableError(409, "Someone kept something under that name at the same moment — try again.")
    logger.info("[deliverable] kept %s v%s in project=%s by %s", row.title, row.version, project.id, getattr(user, "id", None))
    return row


def delete_deliverable(row) -> None:
    """Soft delete: this version goes, the others stay."""
    row.soft_delete()


def _without_content(row) -> dict:
    """Every field but the content -- the one source of truth for both shapes."""
    return {
        "id": str(row.id),
        "project_id": str(row.project_id),
        "title": row.title,
        "kind": row.kind,
        "version": row.version,
        "source_message_id": str(row.source_message_id) if row.source_message_id else None,
        "created_by_id": str(row.created_by_id) if row.created_by_id else None,
        "created_by_name": row.created_by.get_display_name() if row.created_by else None,
        "created_at": row.created_at.isoformat(),
    }


def serialise(row) -> dict:
    return {**_without_content(row), "content": row.content}


def summary(row) -> dict:
    """
    A row for the list. It must never touch `content`: list_deliverables defers
    that column, so reading it here would fetch it again row by row -- the exact
    cost the defer was there to avoid.
    """
    return _without_content(row)
