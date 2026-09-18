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
from typing import List

from ninja import Router
from ninja.errors import HttpError

from authn.auth import SupabaseBearer
from authn.permissions.checker import PermissionChecker
from workspace import services as ws_svc
from intelligence import services as intel_svc
from chat import services as chat_svc
from scheduling import services as sched_svc
from scheduling.schema import ScheduleCreateIn, ScheduleUpdateIn, ScheduleOut

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

    persona = intel_svc.get_persona(company, payload.persona_id)
    if not persona:
        raise HttpError(404, "Persona not found.")

    try:
        result = sched_svc.create_schedule(
            company=company, project=project, topic=topic,
            user=user, persona=persona, payload=payload,
        )
    except ValueError as e:
        raise HttpError(400, str(e))

    label = f" ({payload.label})" if payload.label else ""
    _announce(
        company, project, topic,
        f"\U0001F4C5 Schedule created: @{persona.name}{label} — {result['schedule_summary']}",
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
        _announce(schedule.company, schedule.project, topic, f"Schedule {state}: @{schedule.persona.name}{label}")

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
    persona_name = schedule.persona.name
    sched_svc.delete_schedule(schedule)
    _announce(schedule.company, schedule.project, topic, f"\U0001F5D1️ Schedule deleted: @{persona_name}{label}")
    return {"ok": True}
