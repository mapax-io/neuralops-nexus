"""
scheduling/services.py

Business logic for PersonaSchedule. This layer is the ONLY place that
touches django_celery_beat's models (IntervalSchedule / CrontabSchedule /
ClockedSchedule / PeriodicTask) -- callers (scheduling/api.py,
scheduling/tasks.py) only ever deal with PersonaSchedule.

django-celery-beat is the timing engine, PersonaSchedule is the business
layer on top -- see the model docstring in nucleus/models/scheduling.py
for the full rationale.
"""
import json
from datetime import datetime

from django.utils import timezone as dj_timezone
from django.utils.dateparse import parse_datetime


def _get_or_create_interval(every: int, period: str):
    from django_celery_beat.models import IntervalSchedule
    schedule, _ = IntervalSchedule.objects.get_or_create(every=every, period=period)
    return schedule


def _get_or_create_crontab(minute, hour, day_of_week, day_of_month, month_of_year, tz):
    from django_celery_beat.models import CrontabSchedule
    schedule, _ = CrontabSchedule.objects.get_or_create(
        minute=minute, hour=hour, day_of_week=day_of_week,
        day_of_month=day_of_month, month_of_year=month_of_year,
        timezone=tz,
    )
    return schedule


def _get_or_create_clocked(clocked_time: datetime):
    from django_celery_beat.models import ClockedSchedule
    schedule, _ = ClockedSchedule.objects.get_or_create(clocked_time=clocked_time)
    return schedule


def _human_summary(schedule) -> str:
    """Human-readable one-liner for the frontend list view."""
    from nucleus.models import PersonaSchedule

    if schedule.schedule_kind == PersonaSchedule.ScheduleKind.INTERVAL:
        return f"Every {schedule.interval_every} {schedule.interval_period}"

    if schedule.schedule_kind == PersonaSchedule.ScheduleKind.CRONTAB:
        time_part = f"{schedule.crontab_hour}:{schedule.crontab_minute.zfill(2) if schedule.crontab_minute.isdigit() else schedule.crontab_minute}"
        if schedule.crontab_day_of_week != "*":
            return f"Weekly on day(s) {schedule.crontab_day_of_week} at {time_part} {schedule.timezone}"
        if schedule.crontab_day_of_month != "*":
            return f"Monthly on day {schedule.crontab_day_of_month} at {time_part} {schedule.timezone}"
        return f"Daily at {time_part} {schedule.timezone}"

    if schedule.schedule_kind == PersonaSchedule.ScheduleKind.CLOCKED:
        return f"Once, on {schedule.clocked_time.isoformat()}" if schedule.clocked_time else "Once"

    return schedule.schedule_kind


def _serialise(schedule) -> dict:
    return {
        "id": str(schedule.id),
        "topic_id": str(schedule.topic_id),
        "persona_id": str(schedule.persona_id) if schedule.persona_id else None,
        "persona_name": schedule.persona.name if schedule.persona_id else "",
        "runbook_id": str(schedule.runbook_id) if schedule.runbook_id else None,
        "runbook_title": schedule.runbook.title if schedule.runbook_id else None,
        "query_text": schedule.query_text,
        "label": schedule.label,
        "schedule_kind": schedule.schedule_kind,
        "schedule_summary": _human_summary(schedule),
        "timezone": schedule.timezone,
        "trigger_visible": schedule.trigger_visible,
        "catch_up_missed": schedule.catch_up_missed,
        "is_paused": schedule.is_paused,
        "created_by_id": str(schedule.created_by_id) if schedule.created_by_id else None,
        "last_run_at": schedule.last_run_at.isoformat() if schedule.last_run_at else None,
        "last_status": schedule.last_status,
        "last_error": schedule.last_error,
        "created_at": schedule.created_at.isoformat(),
    }


def create_schedule(*, company, project, topic, user, persona=None, runbook=None, payload) -> dict:
    """
    payload is a scheduling.schema.ScheduleCreateIn (already validated by
    Ninja). Creates the PersonaSchedule row, the matching django-celery-beat
    schedule object (Interval/Crontab/Clocked -- exactly one, based on
    schedule_kind), and the PeriodicTask that links them, in that order,
    inside a transaction. Exactly one of persona / runbook (W6) is set.
    """
    from django.db import transaction
    from nucleus.models import PersonaSchedule
    from django_celery_beat.models import PeriodicTask

    if (persona is None) == (runbook is None):
        raise ValueError("A schedule runs a persona or starts a runbook -- one of the two.")
    if persona is not None and not (payload.query_text or "").strip():
        raise ValueError("Say what the persona should do each run.")

    kind = payload.schedule_kind
    if kind not in (
        PersonaSchedule.ScheduleKind.INTERVAL,
        PersonaSchedule.ScheduleKind.CRONTAB,
        PersonaSchedule.ScheduleKind.CLOCKED,
    ):
        raise ValueError(f"Invalid schedule_kind '{kind}'.")

    if kind == PersonaSchedule.ScheduleKind.INTERVAL:
        if not payload.interval_every or not payload.interval_period:
            raise ValueError("interval_every and interval_period are required for schedule_kind=interval.")
    if kind == PersonaSchedule.ScheduleKind.CLOCKED:
        if not payload.clocked_time:
            raise ValueError("clocked_time is required for schedule_kind=clocked.")
        clocked_dt = parse_datetime(payload.clocked_time)
        if clocked_dt is None:
            raise ValueError("clocked_time must be a valid ISO 8601 datetime.")
        if dj_timezone.is_naive(clocked_dt):
            clocked_dt = dj_timezone.make_aware(clocked_dt, dj_timezone.utc)
        if clocked_dt <= dj_timezone.now():
            raise ValueError("clocked_time must be in the future.")

    with transaction.atomic():
        schedule = PersonaSchedule.objects.create(
            company=company,
            project=project,
            topic=topic,
            persona=persona,
            runbook=runbook,
            created_by=user,
            query_text=(payload.query_text or "").strip() if persona is not None else "",
            label=payload.label,
            schedule_kind=kind,
            interval_every=payload.interval_every,
            interval_period=payload.interval_period,
            crontab_minute=payload.crontab_minute,
            crontab_hour=payload.crontab_hour,
            crontab_day_of_week=payload.crontab_day_of_week,
            crontab_day_of_month=payload.crontab_day_of_month,
            crontab_month_of_year=payload.crontab_month_of_year,
            clocked_time=clocked_dt if kind == PersonaSchedule.ScheduleKind.CLOCKED else None,
            timezone=payload.timezone,
            trigger_visible=payload.trigger_visible,
            catch_up_missed=payload.catch_up_missed,
        )

        pt_kwargs = {
            "name": f"persona-schedule-{schedule.id}",
            "task": "scheduling.tasks.fire_persona_schedule",
            "kwargs": json.dumps({"schedule_id": str(schedule.id)}),
            "enabled": True,
            "one_off": kind == PersonaSchedule.ScheduleKind.CLOCKED,
        }
        if kind == PersonaSchedule.ScheduleKind.INTERVAL:
            pt_kwargs["interval"] = _get_or_create_interval(payload.interval_every, payload.interval_period)
        elif kind == PersonaSchedule.ScheduleKind.CRONTAB:
            pt_kwargs["crontab"] = _get_or_create_crontab(
                payload.crontab_minute, payload.crontab_hour, payload.crontab_day_of_week,
                payload.crontab_day_of_month, payload.crontab_month_of_year, payload.timezone,
            )
        else:
            pt_kwargs["clocked"] = _get_or_create_clocked(clocked_dt)

        periodic_task = PeriodicTask.objects.create(**pt_kwargs)
        schedule.periodic_task = periodic_task
        schedule.save(update_fields=["periodic_task"])

    return _serialise(schedule)


def list_schedules(topic) -> list[dict]:
    from nucleus.models import PersonaSchedule
    schedules = (
        PersonaSchedule.objects.filter(topic=topic, is_active=True)
        .select_related("persona", "runbook")
        .order_by("-created_at")
    )
    return [_serialise(s) for s in schedules]


def get_schedule_object(topic, schedule_id: str):
    """Plain fetch, no permission filtering -- caller decides create.manage vs ownership."""
    from nucleus.models import PersonaSchedule
    return PersonaSchedule.objects.filter(
        topic=topic, id=schedule_id, is_active=True
    ).select_related("persona", "runbook", "periodic_task").first()


def update_schedule(schedule, payload) -> dict:
    """
    payload is a scheduling.schema.ScheduleUpdateIn. Only fields explicitly
    sent (non-None) are applied. Toggling is_paused keeps the underlying
    PeriodicTask.enabled in sync -- that's the actual switch Celery Beat reads.
    """
    fields = []
    if payload.query_text is not None:
        schedule.query_text = payload.query_text
        fields.append("query_text")
    if payload.label is not None:
        schedule.label = payload.label
        fields.append("label")
    if payload.is_paused is not None:
        schedule.is_paused = payload.is_paused
        fields.append("is_paused")
        if schedule.periodic_task_id:
            schedule.periodic_task.enabled = not payload.is_paused
            schedule.periodic_task.save(update_fields=["enabled"])

    if fields:
        schedule.save(update_fields=fields + ["updated_at"])
    return _serialise(schedule)


def delete_schedule(schedule) -> None:
    """
    Soft-deletes the PersonaSchedule (matches every other resource in this
    codebase -- see BaseModel.soft_delete) and hard-deletes the underlying
    PeriodicTask, since that row has no soft-delete concept of its own and
    an orphaned-but-enabled PeriodicTask would otherwise keep firing.
    """
    pt = schedule.periodic_task
    schedule.soft_delete()
    if pt:
        pt.delete()
