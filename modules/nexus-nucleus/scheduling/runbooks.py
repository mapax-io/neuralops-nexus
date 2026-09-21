"""
scheduling/runbooks.py -- Runbooks (W6): an ordered list of persona steps a
project runs as one unit, in one chat, one reply after another.

The definition is a JSON document validated as a whole (validate_runbook_data);
a run is a RunbookRun row the Celery task scheduling.tasks.run_runbook drives
through execute_run(): every step goes through the exact same
chat/services.py:trigger_ai_response_async a live @mention uses, with the
previous step's reply as its context, so a runbook step is indistinguishable
from a person typing "@Persona <prompt>" -- on a queue, unattended. The
starter is the actor of every step (their series of mentions), re-checked
before the first, like a schedule's creator.
"""
import logging
import re
import uuid

from asgiref.sync import async_to_sync
from django.utils import timezone

from chat.stop_signals import stop_signals

logger = logging.getLogger(__name__)

STEPS_MAX = 12
PROMPT_MAX = 4000
TITLE_MAX = 120
DESCRIPTION_MAX = 500
ON_FAILURE = ("stop", "skip", "retry")
# A step's output type is the worker's short token (auto, chart, code, …).
OUTPUT_TYPE_RE = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")
# "retry" gives a failing step ONE more attempt before the stop rule applies.
RETRY_MAX = 1

ACTIVE_STATUSES = ("queued", "running")


# ── Definition ────────────────────────────────────────────────────────────────

def validate_steps(project, steps) -> list[dict]:
    """The stored shape of a runbook's steps; raises ValueError with the reason a person can act on."""
    from nucleus.models import Persona, Routine

    if not isinstance(steps, list) or not 1 <= len(steps) <= STEPS_MAX:
        raise ValueError(f"A runbook has 1 to {STEPS_MAX} steps.")
    personas = {str(p.id) for p in Persona.objects.filter(project=project, is_active=True).only("id")}
    routines = {str(r.id) for r in Routine.objects.filter(project=project, is_active=True).only("id")}
    out = []
    for i, step in enumerate(steps, 1):
        if not isinstance(step, dict):
            raise ValueError(f"Step {i} is not a step.")
        persona_id = str(step.get("persona_id") or "")
        if persona_id not in personas:
            raise ValueError(f"Step {i} names a persona that is not in this project.")
        prompt = (step.get("prompt") or "").strip()
        if not prompt or len(prompt) > PROMPT_MAX:
            raise ValueError(f"Step {i} needs a prompt of at most {PROMPT_MAX:,} characters.")
        routine_id = step.get("routine_id") or None
        if routine_id is not None and str(routine_id) not in routines:
            raise ValueError(f"Step {i} names a routine that is not in this project.")
        output_type = (step.get("output_type") or "auto").strip().lower()
        if not OUTPUT_TYPE_RE.match(output_type):
            raise ValueError(f"Step {i} has an output type the worker cannot resolve.")
        on_failure = step.get("on_failure") or "stop"
        if on_failure not in ON_FAILURE:
            raise ValueError(f"Step {i}: on_failure is stop, skip or retry.")
        out.append({
            "persona_id": persona_id, "prompt": prompt, "routine_id": str(routine_id) if routine_id else None,
            "output_type": output_type, "on_failure": on_failure,
        })
    return out


def validate_runbook_data(project, data: dict, *, partial: bool = False) -> dict:
    out = {}
    if "title" in data or not partial:
        title = (data.get("title") or "").strip()
        if not title or len(title) > TITLE_MAX:
            raise ValueError(f"A runbook needs a title of at most {TITLE_MAX} characters.")
        out["title"] = title
    if "description" in data:
        description = (data.get("description") or "").strip()
        if len(description) > DESCRIPTION_MAX:
            raise ValueError(f"The description is at most {DESCRIPTION_MAX} characters.")
        out["description"] = description
    if "steps" in data or not partial:
        out["steps"] = validate_steps(project, data.get("steps"))
    return out


def list_runbooks(project):
    from nucleus.models import Runbook
    return list(Runbook.objects.filter(project=project, is_active=True).order_by("title"))


def get_runbook(project, runbook_id: str):
    from nucleus.models import Runbook
    return Runbook.objects.filter(project=project, id=runbook_id, is_active=True).first()


def create_runbook(company, project, user, data: dict):
    from nucleus.models import Runbook
    data = validate_runbook_data(project, data)
    return Runbook.objects.create(company=company, project=project, created_by=user, **data)


def patch_runbook(project, runbook_id: str, data: dict):
    runbook = get_runbook(project, runbook_id)
    if not runbook:
        return None
    data = validate_runbook_data(project, {k: v for k, v in data.items() if v is not None}, partial=True)
    for field, value in data.items():
        setattr(runbook, field, value)
    runbook.save()
    return runbook


def delete_runbook(project, runbook_id: str) -> bool:
    """Soft-delete; its runs stay as history."""
    runbook = get_runbook(project, runbook_id)
    if not runbook:
        return False
    runbook.soft_delete()
    return True


def serialise_runbook(runbook, personas: dict | None = None, routines: dict | None = None) -> dict:
    """The definition with each step's persona and routine named as they are NOW (a rename shows)."""
    from nucleus.models import Persona, Routine

    steps = runbook.steps or []
    if personas is None:
        ids = {s.get("persona_id") for s in steps}
        personas = {str(p.id): p.name for p in Persona.objects.filter(id__in=ids)}
    if routines is None:
        ids = {s.get("routine_id") for s in steps if s.get("routine_id")}
        routines = {str(r.id): r.title for r in Routine.objects.filter(id__in=ids)} if ids else {}
    return {
        "id": str(runbook.id),
        "project_id": str(runbook.project_id),
        "title": runbook.title,
        "description": runbook.description or "",
        "steps": [
            {
                **s,
                "persona_name": personas.get(s.get("persona_id")),
                "routine_title": routines.get(s.get("routine_id")) if s.get("routine_id") else None,
            }
            for s in steps
        ],
        "created_by_id": str(runbook.created_by_id) if runbook.created_by_id else None,
        "created_at": runbook.created_at.isoformat(),
    }


def serialise_runbooks(runbooks: list) -> list[dict]:
    from nucleus.models import Persona, Routine

    persona_ids = {s.get("persona_id") for rb in runbooks for s in (rb.steps or [])}
    routine_ids = {s.get("routine_id") for rb in runbooks for s in (rb.steps or []) if s.get("routine_id")}
    personas = {str(p.id): p.name for p in Persona.objects.filter(id__in=persona_ids)} if persona_ids else {}
    routines = {str(r.id): r.title for r in Routine.objects.filter(id__in=routine_ids)} if routine_ids else {}
    return [serialise_runbook(rb, personas, routines) for rb in runbooks]


# ── Runs ──────────────────────────────────────────────────────────────────────

def serialise_run(run) -> dict:
    return {
        "id": str(run.id),
        "runbook_id": str(run.runbook_id),
        "runbook_title": run.runbook.title,
        "project_id": str(run.project_id),
        "topic_id": str(run.topic_id),
        "channel_id": str(run.topic.channel_id),
        "topic_title": run.topic.title,
        "started_by_id": str(run.started_by_id) if run.started_by_id else None,
        "started_by_name": run.started_by.get_display_name() if run.started_by else None,
        "status": run.status,
        "current_step": run.current_step,
        "step_count": len(run.runbook.steps or []),
        "step_results": run.step_results or [],
        "skipped_count": skipped_count(run),
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "ended_at": run.ended_at.isoformat() if run.ended_at else None,
        "error": run.error or "",
        "created_at": run.created_at.isoformat(),
    }


def _runs(project):
    from nucleus.models import RunbookRun
    return RunbookRun.objects.filter(project=project, is_active=True).select_related("runbook", "topic", "started_by")


def list_runs(project, *, runbook_id: str | None = None, topic_id: str | None = None, active: bool = False, limit: int = 50):
    qs = _runs(project)
    if runbook_id:
        qs = qs.filter(runbook_id=runbook_id)
    if topic_id:
        qs = qs.filter(topic_id=topic_id)
    if active:
        qs = qs.filter(status__in=ACTIVE_STATUSES)
    return list(qs.order_by("-created_at")[:limit])


def get_run(project, run_id: str):
    return _runs(project).filter(id=run_id).first()


def start_run(company, project, runbook, actor, topic):
    """A queued run in `topic`; the caller enqueues the task (or executes it, from a schedule)."""
    from nucleus.models import RunbookRun
    return RunbookRun.objects.create(company=company, project=project, runbook=runbook, topic=topic, started_by=actor)


def run_event(run) -> dict:
    """What the topic hears at every transition -- the app's banner and history read it."""
    # Every topic event carries a top-level id (the app's parser insists): the run's.
    return {"type": "runbook_run", "id": str(run.id), "run": serialise_run(run)}


def _announce(run, content: str) -> None:
    from chat import services as chat_svc
    msg = chat_svc.save_system_message(company=run.company, project=run.project, topic=run.topic, content=content)
    chat_svc.publish(chat_svc.topic_channel(str(run.topic_id)), {**msg, "type": "message"})


def _publish_run(run) -> None:
    from chat import services as chat_svc
    chat_svc.publish(chat_svc.topic_channel(str(run.topic_id)), run_event(run))


def stop_run(run, user) -> str:
    """
    "stopped" once the run will go no further, "finished" when it already had.
    A queued run ends here and now; a running one is marked and its current
    reply gets the stop signal -- the loop closes the run when that reply ends
    (or before the next step starts).
    """
    from nucleus.models import ChatMessage, RunbookRun

    if run.status not in ACTIVE_STATUSES:
        return "finished"
    name = user.get_display_name()
    run.error = f"Stopped by {name}"
    if run.status == RunbookRun.Status.QUEUED:
        run.status = RunbookRun.Status.STOPPED
        run.ended_at = timezone.now()
        run.save(update_fields=["status", "error", "ended_at", "updated_at"])
        _announce(run, f"Runbook: {run.runbook.title} stopped by {name} before it started.")
        _publish_run(run)
        return "stopped"
    run.status = RunbookRun.Status.STOPPED
    # Stamped here as well as in _end: if the worker driving this run is already
    # gone, nothing else will ever close the row and the banner reads "stopped"
    # with no end time for good (audit, 2026-09-21).
    run.ended_at = timezone.now()
    run.save(update_fields=["status", "error", "ended_at", "updated_at"])
    pending = ChatMessage.objects.filter(
        topic=run.topic, status=ChatMessage.Status.PENDING, metadata__runbook_run__id=str(run.id),
    ).order_by("-sequence").first()
    if pending:
        async_to_sync(stop_signals().request_stop)(str(pending.id))
    _publish_run(run)
    return "stopped"


# ── Execution (the Celery task's body) ────────────────────────────────────────

def skipped_count(run) -> int:
    """
    How many steps were SKIPPED (their `skip` rule carried the run past a
    failure) -- a run that finished with one did not finish cleanly. Only
    skipped: a failed or stopped step ends the run, and its own status says so.
    """
    return sum(1 for s in (run.step_results or []) if s.get("status") == "skipped")


def _end(run, status: str, *, error: str = "", line: str) -> None:
    run.status = status
    run.error = error or run.error
    run.ended_at = timezone.now()
    run.save(update_fields=["status", "error", "ended_at", "updated_at"])
    _announce(run, line)
    _publish_run(run)


def _after_step(run) -> None:
    """Record the steps recorded so far on the run row and tell the topic."""
    from nucleus.models import RunbookRun
    RunbookRun.objects.filter(id=run.id).update(step_results=run.step_results, updated_at=timezone.now())
    _publish_run(run)


def _run_step(run, step: dict, index: int, count: int, context: str | None, actor) -> tuple[str, str | None, str, str]:
    """One attempt: (status done|failed|stopped, message id, error, content)."""
    from chat import services as chat_svc
    from nucleus.models import ChatMessage, Persona, Routine

    persona = Persona.objects.filter(id=step["persona_id"], project=run.project, is_active=True).select_related("identity_user").first()
    if persona is None:
        return "failed", None, "its persona is no longer in the project", ""
    routine = None
    if step.get("routine_id"):
        routine = Routine.objects.filter(id=step["routine_id"], project=run.project, is_active=True).select_related("model_config").first()
        if routine is None:
            return "failed", None, "its routine is gone", ""
    msg_id = async_to_sync(chat_svc.trigger_ai_response_async)(
        company=run.company, project=run.project, topic=run.topic, persona=persona,
        user_message=step["prompt"], user_message_id=str(uuid.uuid4()), topic_id=str(run.topic_id),
        output_type=step.get("output_type") or "auto",
        interactive=False,  # a runbook has nobody waiting to approve a plan
        routine=routine, triggered_by=actor,
        step_context=context,
        runbook_run={"id": str(run.id), "title": run.runbook.title, "step": index + 1, "of": count},
    )
    row = ChatMessage.objects.filter(id=msg_id).first() if msg_id else None
    if row is None:
        return "failed", msg_id, "no reply was produced", ""
    if (row.metadata or {}).get("stopped"):
        return "stopped", msg_id, "", row.content or ""
    if row.status == ChatMessage.Status.COMPLETED:
        return "done", msg_id, "", row.content or ""
    return "failed", msg_id, row.content or "the reply failed", ""


def execute_run(run_id: str) -> None:
    """Drive a queued run to its end. Sync -- it runs inside a Celery task."""
    from nucleus.models import RunbookRun

    # Claimed, not checked: two deliveries of the same task both read "queued"
    # and both drove every step into the chat (audit, 2026-09-21). Exactly one
    # update can move the row out of QUEUED, and only that one goes on.
    claimed = RunbookRun.objects.filter(id=run_id, status=RunbookRun.Status.QUEUED).update(
        status=RunbookRun.Status.RUNNING, started_at=timezone.now(), updated_at=timezone.now(),
    )
    if not claimed:
        logger.info("[runbook] run %s was not queued, nothing to do", run_id)
        return
    run = RunbookRun.objects.select_related("runbook", "topic", "project", "company", "started_by").filter(id=run_id).first()
    if not run:
        return
    # Every way out of _drive that is not an ending is an ending here. Without
    # this the row stayed RUNNING for ever on a time limit, a DB error or a bug,
    # and the chat showed a runbook mid-flight that nothing would ever close --
    # nothing reaps active runs, and a lost task is not redelivered (audit,
    # 2026-09-21).
    try:
        _drive(run)
    except Exception as exc:  # noqa: BLE001
        logger.exception("[runbook] run %s stopped driving", run_id)
        _end(
            run, RunbookRun.Status.FAILED,
            error=f"The server stopped driving this run: {type(exc).__name__}",
            line=f"Runbook: {run.runbook.title} stopped unexpectedly — the server could not carry it to the end.",
        )
        raise


def _drive(run) -> None:
    """The steps themselves, from the first to whichever one ends the run."""
    from authn.permissions.checker import PermissionChecker
    from nucleus.models import Persona, RunbookRun

    title = run.runbook.title
    steps = run.runbook.steps or []
    count = len(steps)
    actor = run.started_by

    # The starter is the actor of every step -- their right to call personas here is re-checked, as a schedule's is.
    if actor is None:
        reason = "its starter no longer has an account here"
    elif not PermissionChecker.can(actor, "persona.mention", obj=run.topic):
        reason = f"{actor.email or actor.username} can no longer call personas in this chat"
    else:
        reason = None
    if reason:
        _end(run, RunbookRun.Status.FAILED, error=f"Did not start: {reason}.", line=f"Runbook: {title} did not start — {reason}.")
        return

    _announce(run, f"Runbook: {title} started by {actor.get_display_name()} — {count} steps.")
    _publish_run(run)

    names = {str(p.id): p.name for p in Persona.objects.filter(project=run.project, id__in={s["persona_id"] for s in steps})}
    context: str | None = None
    for index, step in enumerate(steps):
        # Stopped from outside between steps: the next one never starts.
        fresh = RunbookRun.objects.filter(id=run.id).values_list("status", flat=True).first()
        if fresh == RunbookRun.Status.STOPPED:
            run.refresh_from_db(fields=["error"])
            how = (run.error[0].lower() + run.error[1:]) if run.error else "stopped"
            _end(run, RunbookRun.Status.STOPPED, line=f"Runbook: {title} {how} after step {index} of {count}.")
            return
        run.current_step = index
        run.save(update_fields=["current_step", "updated_at"])
        _publish_run(run)

        attempts = 0
        started = timezone.now()
        while True:
            attempts += 1
            status, msg_id, error, content = _run_step(run, step, index, count, context, actor)
            if status == "failed" and step.get("on_failure") == "retry" and attempts <= RETRY_MAX:
                continue
            break
        result = {
            "index": index, "persona_id": step["persona_id"], "persona_name": names.get(step["persona_id"]),
            "message_id": msg_id, "status": status, "attempts": attempts,
            "started_at": started.isoformat(), "ended_at": timezone.now().isoformat(), "error": error,
        }
        if status == "failed" and step.get("on_failure") == "skip":
            result["status"] = "skipped"
        run.step_results = [*(run.step_results or []), result]
        _after_step(run)

        if status == "done":
            context = content
            continue
        if status == "stopped":
            run.refresh_from_db(fields=["error"])
            _end(run, RunbookRun.Status.STOPPED, line=f"Runbook: {title} stopped at step {index + 1} of {count}.")
            return
        if step.get("on_failure") == "skip":
            continue  # the next step sees the last GOOD output
        _end(run, RunbookRun.Status.FAILED, error=f"Failed at step {index + 1} of {count}: {error}", line=f"Runbook: {title} failed at step {index + 1} of {count} — {error}")
        return

    # "finished" on its own would hide a skipped step from everyone reading the chat.
    skipped = skipped_count(run)
    _end(run, RunbookRun.Status.DONE, line=f"Runbook: {title} finished — {count} steps" + (f", {skipped} skipped." if skipped else "."))
