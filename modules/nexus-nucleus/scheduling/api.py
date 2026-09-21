"""
scheduling/api.py

CRUD for PersonaSchedule ("automate a persona on a schedule in this
topic"). Mounted under /projects/ in core/urls.py, so full paths are:

    GET    /api/v1/projects/{project_id}/channels/{channel_id}/topics/{topic_id}/schedules/
    POST   /api/v1/projects/{project_id}/channels/{channel_id}/topics/{topic_id}/schedules/
    PATCH  /api/v1/projects/{project_id}/channels/{channel_id}/topics/{topic_id}/schedules/{schedule_id}/
    DELETE /api/v1/projects/{project_id}/channels/{channel_id}/topics/{topic_id}/schedules/{schedule_id}/

Topic resolution/visibility reuses the exact same pattern as
chat/api.py:_resolve_topic_sync (list_channels/list_topics row-visibility,
not a plain ID lookup) -- a topic this user can't see can't be scheduled
against either just because they belong to the parent project.

Permission model (see rights.py for the full rationale comment):
    schedule.create  -- required to create a new schedule in a topic.
    schedule.manage  -- required to pause/resume/delete a schedule you did
                        NOT create. A schedule's own creator can always
                        pause/resume/delete THEIR OWN schedule regardless
                        of holding schedule.manage (see _can_modify below).
"""
from typing import List, Optional

from ninja import Router
from ninja.errors import HttpError

from authn.auth import SupabaseBearer
from authn.permissions.checker import PermissionChecker
from workspace import services as ws_svc
from intelligence import services as intel_svc
from chat import services as chat_svc
from scheduling import runbooks
from scheduling import services as sched_svc
from scheduling.schema import (
    RunbookIn, RunbookOut, RunbookPatchIn, RunbookRunOut, RunbookStartIn, ScheduleCreateIn, ScheduleUpdateIn, ScheduleOut,
)

router = Router(tags=["Scheduling"], auth=SupabaseBearer())


def _announce(company, project, topic, content: str) -> None:
    """
    Post a visible system message into the topic's chat (same mechanism as
    @session open/close in chat/api.py) so a schedule being created, paused,
    resumed, or deleted shows up right in the conversation -- not just in
    the /list-schedules dialog someone has to remember to open. This is
    deliberately separate from PersonaSchedule.trigger_visible, which only
    controls whether each *firing* posts a message -- lifecycle changes to
    the schedule itself always announce, regardless of that setting.
    """
    sys_msg = chat_svc.save_system_message(company=company, project=project, topic=topic, content=content)
    chat_svc.publish(chat_svc.topic_channel(str(topic.id)), {**sys_msg, "type": "message"})


def _resolve_topic(request, project_id: str, channel_id: str, topic_id: str):
    user = request.auth
    company = ws_svc.get_company()
    if not company:
        raise HttpError(503, "Server not initialised.")

    project = ws_svc.get_project(company, user, project_id)
    if not project:
        raise HttpError(404, "Project not found.")

    channel = ws_svc.list_channels(user, project).filter(id=channel_id).first()
    if not channel:
        raise HttpError(404, "Channel not found.")

    topic = ws_svc.list_topics(user, channel).filter(id=topic_id).first()
    if not topic:
        raise HttpError(404, "Topic not found.")

    return company, user, project, channel, topic


def _schedule_what(schedule) -> str:
    """How a schedule's subject reads in a line: the persona, or the runbook it starts (W6)."""
    if schedule.persona_id:
        return f"@{schedule.persona.name}"
    return f"runbook {schedule.runbook.title}" if schedule.runbook_id else "a runbook"


def _can_modify(user, schedule, topic) -> bool:
    """Creator can always modify their own schedule; otherwise schedule.manage is required."""
    if schedule.created_by_id and str(schedule.created_by_id) == str(user.id):
        return True
    return PermissionChecker.can(user, "schedule.manage", obj=topic)


# ── GET /schedules/ — list ──────────────────────────────────────────────────

@router.get(
    "/{project_id}/channels/{channel_id}/topics/{topic_id}/schedules/",
    response=List[ScheduleOut],
)
def list_schedules(request, project_id: str, channel_id: str, topic_id: str):
    """Anyone who can see the topic can see its schedules -- resolving the
    topic below is itself the visibility check, same as GET /messages/."""
    _, user, project, channel, topic = _resolve_topic(request, project_id, channel_id, topic_id)
    return sched_svc.list_schedules(topic)


# ── POST /schedules/ — create ────────────────────────────────────────────────

@router.post(
    "/{project_id}/channels/{channel_id}/topics/{topic_id}/schedules/",
    response=ScheduleOut,
)
def create_schedule(
    request, project_id: str, channel_id: str, topic_id: str, payload: ScheduleCreateIn,
):
    company, user, project, channel, topic = _resolve_topic(request, project_id, channel_id, topic_id)

    if not PermissionChecker.can(user, "schedule.create", obj=topic):
        raise HttpError(403, "You don't have permission to create a schedule in this topic.")
    # A schedule is a standing @mention: the same right the send path checks.
    if not PermissionChecker.can(user, "persona.mention", obj=topic):
        raise HttpError(403, "You don't have permission to call personas in this topic.")

    if bool(payload.persona_id) == bool(payload.runbook_id):
        raise HttpError(400, "A schedule runs a persona or starts a runbook -- one of the two.")
    persona = runbook = None
    if payload.runbook_id:
        # Starting a runbook on a clock is starting a runbook (W6).
        if not PermissionChecker.can(user, "runbook.run", obj=project):
            raise HttpError(403, "You don't have permission to run runbooks in this project.")
        runbook = runbooks.get_runbook(project, payload.runbook_id)
        if not runbook:
            raise HttpError(404, "Runbook not found.")
    else:
        persona = intel_svc.get_persona(company, payload.persona_id)
        if not persona:
            raise HttpError(404, "Persona not found.")

    try:
        result = sched_svc.create_schedule(
            company=company, project=project, topic=topic,
            user=user, persona=persona, runbook=runbook, payload=payload,
        )
    except ValueError as e:
        raise HttpError(400, str(e))

    label = f" ({payload.label})" if payload.label else ""
    what = f"@{persona.name}" if persona is not None else f"runbook {runbook.title}"
    _announce(
        company, project, topic,
        f"\U0001F4C5 Schedule created: {what}{label} — {result['schedule_summary']}",
    )
    return result


# ── PATCH /schedules/{schedule_id}/ — pause / resume / edit ─────────────────

@router.patch(
    "/{project_id}/channels/{channel_id}/topics/{topic_id}/schedules/{schedule_id}/",
    response=ScheduleOut,
)
def update_schedule(
    request, project_id: str, channel_id: str, topic_id: str, schedule_id: str,
    payload: ScheduleUpdateIn,
):
    _, user, project, channel, topic = _resolve_topic(request, project_id, channel_id, topic_id)

    schedule = sched_svc.get_schedule_object(topic, schedule_id)
    if not schedule:
        raise HttpError(404, "Schedule not found.")

    if not _can_modify(user, schedule, topic):
        raise HttpError(403, "You don't have permission to modify this schedule.")

    result = sched_svc.update_schedule(schedule, payload)

    if payload.is_paused is not None:
        label = f" ({schedule.label})" if schedule.label else ""
        state = "paused ⏸" if payload.is_paused else "resumed ▶️"
        _announce(schedule.company, schedule.project, topic, f"Schedule {state}: {_schedule_what(schedule)}{label}")

    return result


# ── DELETE /schedules/{schedule_id}/ ─────────────────────────────────────────

@router.delete("/{project_id}/channels/{channel_id}/topics/{topic_id}/schedules/{schedule_id}/")
def delete_schedule(request, project_id: str, channel_id: str, topic_id: str, schedule_id: str):
    _, user, project, channel, topic = _resolve_topic(request, project_id, channel_id, topic_id)

    schedule = sched_svc.get_schedule_object(topic, schedule_id)
    if not schedule:
        raise HttpError(404, "Schedule not found.")

    if not _can_modify(user, schedule, topic):
        raise HttpError(403, "You don't have permission to delete this schedule.")

    label = f" ({schedule.label})" if schedule.label else ""
    what = _schedule_what(schedule)
    sched_svc.delete_schedule(schedule)
    _announce(schedule.company, schedule.project, topic, f"\U0001F5D1️ Schedule deleted: {what}{label}")
    return {"ok": True}


# ── Runbooks (W6) ─────────────────────────────────────────────────────────────
# Mounted under /projects/ like the schedules above:
#     GET/POST   /api/v1/projects/{project_id}/runbooks/
#     PATCH/DEL  /api/v1/projects/{project_id}/runbooks/{runbook_id}/
#     POST       /api/v1/projects/{project_id}/runbooks/{runbook_id}/run/
#     GET        /api/v1/projects/{project_id}/runbooks/runs/?runbook_id=&topic_id=&active=
#     POST       /api/v1/projects/{project_id}/runbooks/runs/{run_id}/stop/
# Reading needs the project (topic.list, as routines); defining is
# runbook.manage (Admin); starting and stopping is runbook.run (Member) plus
# the right to call personas in the topic -- a run is a series of mentions.

def _runbook_project(request, project_id: str, right: str):
    user = request.auth
    company = ws_svc.get_company()
    if not company:
        raise HttpError(503, "Server not initialised.")
    project = ws_svc.get_project_object(company, project_id)
    if not project:
        raise HttpError(404, "Project not found.")
    if not PermissionChecker.can(user, right, obj=project):
        raise HttpError(403, {
            "runbook.manage": "You don't have permission to define runbooks here.",
            "runbook.run": "You don't have permission to run runbooks here.",
        }.get(right, "You don't have access to this project."))
    return company, user, project


@router.get("/{project_id}/runbooks/", response=List[RunbookOut])
def list_runbooks(request, project_id: str):
    _, _, project = _runbook_project(request, project_id, "topic.list")
    return runbooks.serialise_runbooks(runbooks.list_runbooks(project))


@router.post("/{project_id}/runbooks/", response=RunbookOut)
def create_runbook(request, project_id: str, payload: RunbookIn):
    company, user, project = _runbook_project(request, project_id, "runbook.manage")
    try:
        return runbooks.serialise_runbook(runbooks.create_runbook(company, project, user, payload.dict()))
    except ValueError as e:
        raise HttpError(400, str(e))


# The fixed `runs/` paths register BEFORE `{runbook_id}/` -- the resolver takes the first pattern that matches.
@router.get("/{project_id}/runbooks/runs/", response=List[RunbookRunOut])
def list_runbook_runs(request, project_id: str, runbook_id: Optional[str] = None, topic_id: Optional[str] = None, active: Optional[str] = None):
    _, _, project = _runbook_project(request, project_id, "topic.list")
    return [runbooks.serialise_run(r) for r in runbooks.list_runs(project, runbook_id=runbook_id, topic_id=topic_id, active=bool(active))]


@router.post("/{project_id}/runbooks/runs/{run_id}/stop/", response=RunbookRunOut)
def stop_runbook_run(request, project_id: str, run_id: str):
    _, user, project = _runbook_project(request, project_id, "runbook.run")
    run = runbooks.get_run(project, run_id)
    if not run:
        raise HttpError(404, "Run not found.")
    if runbooks.stop_run(run, user) == "finished":
        raise HttpError(409, "This run has already ended.")
    return runbooks.serialise_run(runbooks.get_run(project, run_id))


@router.patch("/{project_id}/runbooks/{runbook_id}/", response=RunbookOut)
def patch_runbook(request, project_id: str, runbook_id: str, payload: RunbookPatchIn):
    _, _, project = _runbook_project(request, project_id, "runbook.manage")
    try:
        runbook = runbooks.patch_runbook(project, runbook_id, payload.dict(exclude_none=True))
    except ValueError as e:
        raise HttpError(400, str(e))
    if not runbook:
        raise HttpError(404, "Runbook not found.")
    return runbooks.serialise_runbook(runbook)


@router.delete("/{project_id}/runbooks/{runbook_id}/", response={204: None})
def delete_runbook(request, project_id: str, runbook_id: str):
    _, _, project = _runbook_project(request, project_id, "runbook.manage")
    if not runbooks.delete_runbook(project, runbook_id):
        raise HttpError(404, "Runbook not found.")
    return 204, None


@router.post("/{project_id}/runbooks/{runbook_id}/run/", response=RunbookRunOut)
def start_runbook(request, project_id: str, runbook_id: str, payload: RunbookStartIn):
    """Run now -- in a topic the starter can call personas in, or a new one in a channel they can create topics in."""
    from scheduling.tasks import run_runbook

    company, user, project = _runbook_project(request, project_id, "runbook.run")
    runbook = runbooks.get_runbook(project, runbook_id)
    if not runbook:
        raise HttpError(404, "Runbook not found.")
    if bool(payload.topic_id) == bool(payload.channel_id):
        raise HttpError(400, "Say where to run it: a topic, or a channel for a new one.")
    if payload.topic_id:
        topic = None
        for channel in ws_svc.list_channels(user, project):
            topic = ws_svc.list_topics(user, channel).filter(id=payload.topic_id).first()
            if topic:
                break
        if not topic:
            raise HttpError(404, "Topic not found.")
    else:
        channel = ws_svc.list_channels(user, project).filter(id=payload.channel_id).first()
        if not channel:
            raise HttpError(404, "Channel not found.")
        if not PermissionChecker.can(user, "topic.create", obj=channel):
            raise HttpError(403, "You don't have permission to create topics in this channel.")
        title = (payload.title or "").strip() or runbook.title
        topic = ws_svc.create_topic(company=company, project=project, channel=channel, title=title[:200], creator=user)
    if not PermissionChecker.can(user, "persona.mention", obj=topic):
        raise HttpError(403, "You don't have permission to call personas in this topic.")
    run = runbooks.start_run(company, project, runbook, user, topic)
    run_runbook.delay(str(run.id))
    return runbooks.serialise_run(runbooks.get_run(project, str(run.id)))
