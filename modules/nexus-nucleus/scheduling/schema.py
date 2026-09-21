from typing import Optional

from ninja import Schema


class ScheduleCreateIn(Schema):
    # Exactly one of persona_id / runbook_id: a schedule runs a persona's
    # query, or starts a runbook (W6; query_text is unused then).
    persona_id: Optional[str] = None
    runbook_id: Optional[str] = None
    query_text: str = ""
    label: str = ""

    schedule_kind: str  # "interval" | "crontab" | "clocked"

    # interval
    interval_every: Optional[int] = None
    interval_period: Optional[str] = None  # "minutes" | "hours" | "days" | "weeks"

    # crontab -- defaults ("0 * * * * *" equivalent-ish) match
    # django_celery_beat.CrontabSchedule's own defaults (every minute) so an
    # omitted field doesn't silently mean something unexpected.
    crontab_minute: str = "0"
    crontab_hour: str = "*"
    crontab_day_of_week: str = "*"
    crontab_day_of_month: str = "*"
    crontab_month_of_year: str = "*"

    # clocked -- ISO 8601 datetime string, one-time fire
    clocked_time: Optional[str] = None

    timezone: str = "UTC"
    trigger_visible: bool = True
    catch_up_missed: bool = True


class ScheduleUpdateIn(Schema):
    """Partial update -- only fields the caller sends are applied."""
    query_text: Optional[str] = None
    label: Optional[str] = None
    is_paused: Optional[bool] = None


class ScheduleOut(Schema):
    id: str
    topic_id: str
    persona_id: Optional[str] = None      # None when the schedule starts a runbook
    persona_name: str = ""
    runbook_id: Optional[str] = None
    runbook_title: Optional[str] = None
    query_text: str
    label: str
    schedule_kind: str
    schedule_summary: str  # human-readable, e.g. "Daily at 09:00 UTC"
    timezone: str
    trigger_visible: bool
    catch_up_missed: bool
    is_paused: bool
    created_by_id: Optional[str] = None
    last_run_at: Optional[str] = None
    last_status: str
    last_error: Optional[str] = None
    created_at: str


# ── Runbooks (W6) ─────────────────────────────────────────────────────────────

class RunbookStepIn(Schema):
    persona_id: str
    prompt: str
    routine_id: Optional[str] = None
    output_type: str = "auto"
    on_failure: str = "stop"   # stop | skip | retry


class RunbookIn(Schema):
    title: str
    description: str = ""
    steps: list[RunbookStepIn]


class RunbookPatchIn(Schema):
    title: Optional[str] = None
    description: Optional[str] = None
    steps: Optional[list[RunbookStepIn]] = None


class RunbookStepOut(Schema):
    persona_id: str
    persona_name: Optional[str] = None   # as the persona is named now; None once it is gone
    prompt: str
    routine_id: Optional[str] = None
    routine_title: Optional[str] = None
    output_type: str
    on_failure: str


class RunbookOut(Schema):
    id: str
    project_id: str
    title: str
    description: str
    steps: list[RunbookStepOut]
    created_by_id: Optional[str] = None
    created_at: str


class RunbookStartIn(Schema):
    """Where to run: this topic, or a new one in a channel (titled after the runbook by default)."""
    topic_id: Optional[str] = None
    channel_id: Optional[str] = None
    title: Optional[str] = None


class RunbookRunOut(Schema):
    id: str
    runbook_id: str
    runbook_title: str
    project_id: str
    topic_id: str
    channel_id: str
    topic_title: str
    started_by_id: Optional[str] = None
    started_by_name: Optional[str] = None
    status: str                 # queued | running | done | failed | stopped
    current_step: int           # 0-based; -1 before the first step
    step_count: int
    step_results: list          # [{index, persona_id, persona_name, message_id, status, attempts, started_at, ended_at, error}]
    skipped_count: int = 0      # steps that did not complete -- a "done" run with one is not a clean one
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    error: str = ""
    created_at: str
