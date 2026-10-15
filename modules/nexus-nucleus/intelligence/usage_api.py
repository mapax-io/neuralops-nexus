"""
Usage read API — "what did the AI cost?" (Step 1, docs/NUCLEUS-REVAMP.md §2.4).

Three windows, three gates (owner's ruling O2):
  topic totals    — anyone who can SEE the topic (resolving it is the check,
                    same as GET /messages/)
  project rollup  — usage.view_project on the project
  company rollup  — usage.view_company on the company

Every money number here is an ESTIMATE: prices come from the online catalog
or an admin override, never from the provider's invoice. Every response says
so (`price_estimated: true` + a plain note) — the owner's ruling O1.
"""
from django.db.models import Count, Q, Sum
from ninja import Router
from ninja.errors import HttpError

from authn.auth import SupabaseBearer
from authn.permissions.checker import PermissionChecker
from nucleus.models import UsageRecord
from workspace import services as ws_svc

# Project- and topic-scoped reads, mounted at /projects/ like chat/scheduling.
router = Router(tags=["Usage"], auth=SupabaseBearer())
# The one company-wide read, mounted at /usage/.
company_router = Router(tags=["Usage"], auth=SupabaseBearer())

ESTIMATE_NOTE = "Estimated — prices not confirmed."


def _money(qs) -> dict:
    """Token and cost totals for any UsageRecord queryset, in the one shape
    every endpoint returns. cost is a string (JSON has no Decimal) or null
    when NO priced row exists; unpriced_rows says how many rows have no
    price at all, so the UI can say 'at least this much'.
    Aggregate aliases must not reuse column names (cost=Sum("cost") makes
    the Q(cost__isnull=...) filter hit the aggregate — FieldError)."""
    agg = qs.aggregate(
        total_in=Sum("input_tokens"),
        total_out=Sum("output_tokens"),
        total_cost=Sum("cost"),
        row_count=Count("id"),
        unpriced=Count("id", filter=Q(cost__isnull=True)),
    )
    return {
        "input_tokens": int(agg["total_in"] or 0),
        "output_tokens": int(agg["total_out"] or 0),
        "cost": str(agg["total_cost"]) if agg["total_cost"] is not None else None,
        "rows": int(agg["row_count"] or 0),
        "unpriced_rows": int(agg["unpriced"] or 0),
    }


def _breakdown(qs, key: str) -> list[dict]:
    """The same totals grouped by one id column, biggest spender first."""
    rows = (
        qs.values(key)
        .annotate(
            total_in=Sum("input_tokens"),
            total_out=Sum("output_tokens"),
            total_cost=Sum("cost"),
            row_count=Count("id"),
            unpriced=Count("id", filter=Q(cost__isnull=True)),
        )
        .order_by("-total_cost")
    )
    return [
        {
            key: r[key],
            "input_tokens": int(r["total_in"] or 0),
            "output_tokens": int(r["total_out"] or 0),
            "cost": str(r["total_cost"]) if r["total_cost"] is not None else None,
            "rows": int(r["row_count"] or 0),
            "unpriced_rows": int(r["unpriced"] or 0),
        }
        for r in rows
    ]


def _project_or_403(request, project_id: str):
    user = request.auth
    company = ws_svc.get_company()
    if not company:
        raise HttpError(503, "Server not initialised.")
    project = ws_svc.get_project(company, user, project_id)
    if not project:
        raise HttpError(404, "Project not found.")
    return company, user, project


# ── Topic totals — visible to everyone in the topic ──────────────────────────

@router.get("/{project_id}/channels/{channel_id}/topics/{topic_id}/usage/", response=dict)
def topic_usage(request, project_id: str, channel_id: str, topic_id: str):
    """What this conversation has cost so far. Resolving the topic through the
    same row-visibility as the sidebar IS the gate — no extra right needed."""
    _, user, project = _project_or_403(request, project_id)
    channel = ws_svc.list_channels(user, project).filter(id=channel_id).first()
    if not channel:
        raise HttpError(404, "Channel not found.")
    topic = ws_svc.list_topics(user, channel).filter(id=topic_id).first()
    if not topic:
        raise HttpError(404, "Topic not found.")

    totals = _money(UsageRecord.objects.filter(topic_id=str(topic.id)))
    return {
        "topic_id": str(topic.id),
        **totals,
        "by_persona": _breakdown(
            UsageRecord.objects.filter(topic_id=str(topic.id)), "persona_id"),
        "price_estimated": True,
        "note": ESTIMATE_NOTE,
    }


# ── Project rollup — usage.view_project ───────────────────────────────────────

@router.get("/{project_id}/usage/", response=dict)
def project_usage(request, project_id: str):
    """The project's bill, split per persona and per model."""
    _, user, project = _project_or_403(request, project_id)
    if not PermissionChecker.can(user, "usage.view_project", obj=project):
        raise HttpError(403, "You don't have permission to view this project's usage.")

    qs = UsageRecord.objects.filter(project_id=str(project.id))
    return {
        "project_id": str(project.id),
        **_money(qs),
        "by_persona": _breakdown(qs, "persona_id"),
        "by_model": _breakdown(qs, "model_id"),
        "price_estimated": True,
        "note": ESTIMATE_NOTE,
    }


# ── Company rollup — usage.view_company ───────────────────────────────────────

@company_router.get("/company/", response=dict)
def company_usage(request):
    """The whole install's bill, split per project and per model. This is the
    local budget view the owner asked for — full detail stays HERE; only the
    single total-tokens figure ever leaves the box (handoff change 13.6)."""
    user = request.auth
    company = ws_svc.get_company()
    if not company:
        raise HttpError(503, "Server not initialised.")
    if not PermissionChecker.can(user, "usage.view_company", company=company):
        raise HttpError(403, "You don't have permission to view company usage.")

    qs = UsageRecord.objects.filter(company_id=str(company.id))
    return {
        "company_id": str(company.id),
        **_money(qs),
        "by_project": _breakdown(qs, "project_id"),
        "by_model": _breakdown(qs, "model_id"),
        "price_estimated": True,
        "note": ESTIMATE_NOTE,
    }
