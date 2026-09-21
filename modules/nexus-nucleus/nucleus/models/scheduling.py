from django.conf import settings
from django.db import models

from .base import ProjectBaseModel


class PersonaSchedule(ProjectBaseModel):
    """
    A recurring or one-off automated query against an existing Persona,
    fired inside an existing ChatTopic without any user present.

    This model holds the business data (who, what, where, how often) --
    it does NOT do any scheduling math itself. The actual "when does this
    next fire" mechanics are delegated to django-celery-beat's own models
    (IntervalSchedule / CrontabSchedule / ClockedSchedule), one of which
    this row points at via periodic_task. django-celery-beat is the timing
    engine; PersonaSchedule is the domain layer on top -- same separation
    already used everywhere else in this codebase (e.g. MCPServer holds
    config, pydantic_ai_runner.py does the actual subprocess mechanics).

    Non-repeating "a few specific dates" is intentionally NOT its own
    schedule_kind -- it's just multiple schedule_kind=clocked rows, one per
    date. Keeps the one-row-to-one-PeriodicTask pairing simple; the UI can
    offer "add another date" as a convenience that creates several rows in
    one action.

    When periodic_task fires, scheduling/tasks.py's Celery task runs,
    posts a visible "Scheduled: <query_text>" ChatMessage (if
    trigger_visible=True) into `topic`, then calls the exact same
    trigger_ai_response_async() pipeline a live @mention uses -- so a
    scheduled run is indistinguishable from a normal one from nexus-ai's
    point of view.
    """

    class ScheduleKind(models.TextChoices):
        INTERVAL = "interval", "Interval (every N hours/minutes)"
        CRONTAB  = "crontab",  "Crontab (daily/weekly/monthly/specific weekdays)"
        CLOCKED  = "clocked",  "Clocked (one-time, a single specific date)"

    class RunStatus(models.TextChoices):
        NEVER_RUN = "never_run", "Never run"
        SUCCESS   = "success",   "Success"
        FAILED    = "failed",    "Failed"

    # -- What to run, and where -------------------------------------------
    topic = models.ForeignKey(
        "nucleus.ChatTopic",
        on_delete=models.CASCADE,
        related_name="persona_schedules",
        help_text="The chat topic this scheduled query fires into.",
    )

    persona = models.ForeignKey(
        "nucleus.Persona",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="schedules",
        help_text="Existing persona to run the query against -- old or new, no restriction. "
                   "Null when the schedule starts a runbook instead (W6).",
    )

    # W6: a schedule may start a runbook instead of one persona -- exactly one
    # of persona / runbook is set (enforced in scheduling/services.py).
    runbook = models.ForeignKey(
        "nucleus.Runbook",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="schedules",
        help_text="The runbook this schedule starts each fire; the query_text is unused then.",
    )

    query_text = models.TextField(
        help_text="The prompt sent to the persona each time this schedule fires.",
    )

    label = models.CharField(
        max_length=255,
        blank=True,
        help_text="Optional short display name for this schedule. Falls back to a "
                   "truncated query_text in the UI if left blank.",
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_schedules",
    )

    # -- Timing (mirrors django-celery-beat's schedule types) ---------------
    schedule_kind = models.CharField(
        max_length=20,
        choices=ScheduleKind.choices,
        db_index=True,
    )

    # ScheduleKind.INTERVAL -- e.g. "every 2 hours"
    interval_every = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="e.g. 1 for 'every 1 hour'. Only used when schedule_kind=interval.",
    )
    interval_period = models.CharField(
        max_length=20,
        null=True, blank=True,
        help_text="django_celery_beat.IntervalSchedule.PERIOD_CHOICES value, "
                   "e.g. 'hours', 'minutes'. Only used when schedule_kind=interval.",
    )

    # ScheduleKind.CRONTAB -- daily/weekly/monthly, or specific weekdays via
    # comma-list day_of_week (e.g. "1,4" = every Monday and Thursday).
    crontab_minute        = models.CharField(max_length=64, default="0", blank=True)
    crontab_hour          = models.CharField(max_length=64, default="*", blank=True)
    crontab_day_of_week   = models.CharField(max_length=64, default="*", blank=True)
    crontab_day_of_month  = models.CharField(max_length=64, default="*", blank=True)
    crontab_month_of_year = models.CharField(max_length=64, default="*", blank=True)

    # ScheduleKind.CLOCKED -- exactly one non-repeating date. Several
    # specific dates = several rows with this kind, not a list on one row.
    clocked_time = models.DateTimeField(
        null=True, blank=True,
        help_text="Exact one-time fire datetime (UTC). Only used when schedule_kind=clocked.",
    )

    timezone = models.CharField(
        max_length=64,
        default="UTC",
        help_text="IANA timezone name the schedule's times are interpreted in, "
                   "e.g. 'America/Edmonton'.",
    )

    # -- Behavior ------------------------------------------------------------
    trigger_visible = models.BooleanField(
        default=True,
        help_text="If True, post a visible 'Scheduled: <query>' message before the "
                   "persona replies, same as a normal @mention. If False, only the "
                   "persona's reply appears.",
    )

    catch_up_missed = models.BooleanField(
        default=True,
        help_text="If True, a run missed while the server was down fires once on "
                   "restart. If False, missed runs are skipped -- only the next "
                   "regularly scheduled occurrence fires.",
    )

    is_paused = models.BooleanField(
        default=False,
        help_text="User-facing pause switch, distinct from is_active (soft delete). "
                   "A paused schedule's periodic_task.enabled is kept in sync to False.",
    )

    # -- Link to the django-celery-beat row that actually drives timing -----
    periodic_task = models.OneToOneField(
        "django_celery_beat.PeriodicTask",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="persona_schedule",
        help_text="The PeriodicTask row whose schedule + enabled flag this row keeps "
                   "in sync with. Created/updated/deleted by scheduling/services.py, "
                   "never edited directly.",
    )

    # -- Bookkeeping ----------------------------------------------------------
    last_run_at = models.DateTimeField(null=True, blank=True)
    last_status = models.CharField(
        max_length=20,
        choices=RunStatus.choices,
        default=RunStatus.NEVER_RUN,
    )
    last_error = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "workspace_persona_schedule"
        indexes = [
            models.Index(fields=["company", "project", "topic"]),
            models.Index(fields=["persona"]),
            models.Index(fields=["is_active", "is_paused"]),
        ]
        constraints = [
            models.CheckConstraint(
                name="schedule_interval_requires_fields",
                condition=(
                    ~models.Q(schedule_kind="interval")
                    | (models.Q(interval_every__isnull=False) & models.Q(interval_period__isnull=False))
                ),
            ),
            models.CheckConstraint(
                name="schedule_clocked_requires_time",
                condition=(
                    ~models.Q(schedule_kind="clocked")
                    | models.Q(clocked_time__isnull=False)
                ),
            ),
        ]

    def __str__(self):
        what = self.persona.name if self.persona_id else f"runbook {self.runbook.title if self.runbook_id else '?'}"
        return f"{what} @ {self.topic.title} ({self.schedule_kind})"


class InboundHook(ProjectBaseModel):
    """
    A URL another system POSTs to so a persona answers in a topic, with nobody
    signed in (W12): build monitors, alert managers, cron jobs, form handlers.

    The token is never stored -- only its sha256 and its last four characters,
    which is all a person needs to tell two hooks apart. A fire acts as the
    person who created the hook: their right to call personas in the topic is
    re-checked every time, exactly as a schedule's creator's is.
    """

    class FireStatus(models.TextChoices):
        NEVER_FIRED = "never_fired", "Never fired"
        SUCCESS = "success", "Success"
        FAILED = "failed", "Failed"

    topic = models.ForeignKey(
        "nucleus.ChatTopic", on_delete=models.CASCADE, related_name="inbound_hooks",
        help_text="The chat a fire posts into.",
    )
    persona = models.ForeignKey(
        "nucleus.Persona", on_delete=models.CASCADE, related_name="inbound_hooks",
        help_text="The persona a fire calls.",
    )
    label = models.CharField(
        max_length=80, blank=True, default="",
        help_text="What sends to this hook -- shown in the pane, never to the sender.",
    )
    token_hash = models.CharField(
        max_length=64, unique=True, db_index=True,
        help_text="sha256 of the token. The token itself is shown once, at creation, and never stored.",
    )
    token_hint = models.CharField(
        max_length=8, blank=True, default="",
        help_text="The token's last few characters, so two hooks can be told apart.",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="created_hooks",
    )
    # The disable switch a person flips, distinct from is_active (soft delete) --
    # the same split PersonaSchedule makes.
    is_paused = models.BooleanField(default=False)
    last_fired_at = models.DateTimeField(null=True, blank=True)
    fire_count = models.PositiveIntegerField(default=0)
    last_status = models.CharField(max_length=20, choices=FireStatus.choices, default=FireStatus.NEVER_FIRED)
    last_error = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["topic", "is_active"])]

    def __str__(self) -> str:
        return f"hook -> @{self.persona.name} in {self.topic.title}"


class Runbook(ProjectBaseModel):
    """
    An ordered list of persona steps a project runs as one unit (W6). Each
    step names a persona and a prompt, optionally a routine (its instructions,
    tool narrowing and model) and an output type, and what to do when it
    fails. The steps are a JSON list validated in scheduling/runbooks.py --
    a runbook is edited as one document, never step by step.
    """

    title = models.CharField(max_length=120)
    description = models.CharField(max_length=500, blank=True, default="")
    # [{persona_id, prompt, routine_id | null, output_type, on_failure}] -- 1 to 12 steps.
    steps = models.JSONField(default=list)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="created_runbooks",
    )

    class Meta:
        ordering = ["title"]
        indexes = [models.Index(fields=["project", "is_active"])]

    def __str__(self) -> str:
        return f"{self.title} ({len(self.steps or [])} steps)"


class RunbookRun(ProjectBaseModel):
    """
    One execution of a runbook in one topic: which step is running, how each
    step went, and who started it (the actor of every step's mention).
    """

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        DONE = "done", "Done"
        FAILED = "failed", "Failed"
        STOPPED = "stopped", "Stopped"

    runbook = models.ForeignKey(Runbook, on_delete=models.CASCADE, related_name="runs")
    topic = models.ForeignKey("nucleus.ChatTopic", on_delete=models.CASCADE, related_name="runbook_runs")
    started_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="started_runbook_runs",
    )
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.QUEUED, db_index=True)
    # 0-based index of the step in progress; -1 before the first starts.
    current_step = models.IntegerField(default=-1)
    # [{index, persona_id, persona_name, message_id, status, started_at, ended_at, error}] in step order.
    step_results = models.JSONField(default=list)
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    error = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["runbook", "status"]), models.Index(fields=["topic", "status"])]

    def __str__(self) -> str:
        return f"{self.runbook.title} run ({self.status})"
