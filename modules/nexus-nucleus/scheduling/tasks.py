"""
scheduling/tasks.py

The Celery task a fired PeriodicTask actually runs. Celery Beat (reading
from the DB via CELERY_BEAT_SCHEDULER=DatabaseScheduler, see core/settings.py)
enqueues this by name -- "scheduling.tasks.fire_persona_schedule" -- exactly
as set in PeriodicTask.task by scheduling/services.py:create_schedule().

This task deliberately does NOT reimplement any part of the AI-trigger
pipeline. It posts a visible "Scheduled: ..." system message (same as any
other system event -- session opened/closed, etc.) and then hands off to
chat/services.py:trigger_ai_response_async(), the exact same function a
live @mention uses. From nexus-ai's point of view, and from the chat
history's point of view, a scheduled fire is indistinguishable from a
human typing "@Persona <query>" -- which is the point: the whole feature
is "make it possible to do that on a timer, unattended."

Celery tasks are sync by default (this worker isn't running an event
loop), so the async pipeline is invoked via asgiref.sync.async_to_sync.
"""
import logging
import uuid

from asgiref.sync import async_to_sync
from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(name="scheduling.tasks.fire_persona_schedule")
def fire_persona_schedule(schedule_id: str) -> None:
    from authn.permissions.checker import PermissionChecker
    from nucleus.models import PersonaSchedule
    from chat import services as chat_svc

    schedule = (
        PersonaSchedule.objects.filter(id=schedule_id, is_active=True)
        .select_related("topic", "project", "company", "persona", "persona__identity_user", "created_by")
        .first()
    )
    if not schedule:
        logger.warning("[scheduling] fire_persona_schedule: schedule %s not found or inactive", schedule_id)
        return

    if schedule.is_paused:
        # Shouldn't normally happen -- pausing disables the PeriodicTask
        # itself (see services.py:update_schedule) -- but guard against a
        # race where a pause landed between Beat's dispatch and this
        # worker picking the task up.
        logger.info("[scheduling] fire_persona_schedule: schedule %s is paused, skipping", schedule_id)
        return

    topic = schedule.topic
    project = schedule.project
    company = schedule.company
    persona = schedule.persona

    channel_name = chat_svc.topic_channel(str(topic.id))

    # The creator is the actor of every fire -- a schedule is their standing
    # @mention, so it stops when they can no longer call personas here (or are
    # gone). Announced topic-wide like every other schedule event, and recorded
    # on the schedule so the list shows why it did not run.
    actor = schedule.created_by
    if actor is None:
        skip = "its creator no longer has an account here"
    elif not PermissionChecker.can(actor, "persona.mention", obj=topic):
        skip = f"{actor.email or actor.username} can no longer call personas in this topic"
    else:
        skip = None
    if skip:
        logger.warning("[scheduling] fire_persona_schedule: schedule %s skipped: %s", schedule_id, skip)
        sys_msg = chat_svc.save_system_message(
            company=company, project=project, topic=topic,
            content=f"Scheduled run of @{persona.name} skipped: {skip}.",
        )
        chat_svc.publish(channel_name, {**sys_msg, "type": "message"})
        PersonaSchedule.objects.filter(id=schedule.id).update(
            last_run_at=timezone.now(),
            last_status=PersonaSchedule.RunStatus.FAILED,
            last_error=f"Skipped: {skip}."[:2000],
        )
        return

    try:
        if schedule.trigger_visible:
            label = f" ({schedule.label})" if schedule.label else ""
            sys_msg = chat_svc.save_system_message(
                company=company, project=project, topic=topic,
                content=f"Scheduled: @{persona.name} {schedule.query_text}{label}",
            )
            chat_svc.publish(channel_name, {**sys_msg, "type": "message"})

        # Fake a "user_message_id" -- there is no real human ChatMessage
        # behind a scheduled fire (unlike a live @mention, see chat/api.py),
        # so trigger_ai_response_async gets a fresh uuid it can still log/
        # reference; nothing downstream dereferences it as a real row.
        async_to_sync(chat_svc.trigger_ai_response_async)(
            company=company,
            project=project,
            topic=topic,
            persona=persona,
            user_message=schedule.query_text,
            user_message_id=str(uuid.uuid4()),
            topic_id=str(topic.id),
            output_type="auto",
            interactive=False,  # a schedule has nobody waiting to approve a plan
            triggered_by=schedule.created_by,  # the reply is the creator's to stop (W22)
        )

        PersonaSchedule.objects.filter(id=schedule.id).update(
            last_run_at=timezone.now(),
            last_status=PersonaSchedule.RunStatus.SUCCESS,
            last_error=None,
        )

    except Exception as exc:  # noqa: BLE001
        logger.exception("[scheduling] fire_persona_schedule failed for schedule %s", schedule_id)
        PersonaSchedule.objects.filter(id=schedule.id).update(
            last_run_at=timezone.now(),
            last_status=PersonaSchedule.RunStatus.FAILED,
            last_error=str(exc)[:2000],
        )
