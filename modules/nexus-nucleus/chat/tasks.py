"""
chat/tasks.py — pause expiry (Step 3, handoff change 9).

A paused reply waits for a person — but not forever. Once a PausedRun is
older than PAUSE_EXPIRY_HOURS, this hourly task fills in every undecided
call (deny for approvals, an explicit "nobody answered" line for questions)
and resumes the run. The engine turns those into worded tool results and the
reply COMPLETES with "was not approved" instead of hanging as a parked
bubble for weeks.

(The old chat/tasks.py — Celery-driven AI responses from 0.7 — was retired
in Step 0; this file is new, for this one job.)
"""
from __future__ import annotations

import logging
from datetime import timedelta

from asgiref.sync import async_to_sync
from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)

PAUSE_EXPIRY_HOURS = 24

EXPIRED_APPROVAL_REASON = "expired — nobody decided within 24 hours"
EXPIRED_QUESTION_ANSWER = "(no answer — this question expired after 24 hours with nobody answering)"


@shared_task(name="chat.tasks.expire_paused_runs")
def expire_paused_runs() -> str:
    """Resume-with-deny every paused run past the expiry window."""
    from chat.relay import resume_paused_run
    from nucleus.models import PausedRun

    cutoff = timezone.now() - timedelta(hours=PAUSE_EXPIRY_HOURS)
    expired = list(PausedRun.objects.filter(created_at__lt=cutoff))
    resumed = 0
    for run in expired:
        decisions = dict(run.decisions or {})
        for item in (run.pending or []):
            call_id = item.get("call_id")
            if not call_id or call_id in decisions:
                continue
            if item.get("kind") == "question":
                decisions[call_id] = {"kind": "question", "answer": EXPIRED_QUESTION_ANSWER,
                                      "decided_by_name": "expiry", "decided_at": timezone.now().isoformat()}
            else:
                decisions[call_id] = {"kind": "approval", "decision": "deny",
                                      "reason": EXPIRED_APPROVAL_REASON,
                                      "decided_by_name": "expiry", "decided_at": timezone.now().isoformat()}
        PausedRun.objects.filter(id=run.id).update(decisions=decisions)
        try:
            async_to_sync(resume_paused_run)(run.message_id)
            resumed += 1
        except Exception as exc:  # noqa: BLE001 — one broken run must not strand the rest
            logger.warning("[pause-expiry] resume failed for %s: %s", run.message_id, exc)
    if expired:
        logger.info("[pause-expiry] resumed %d of %d expired paused runs", resumed, len(expired))
    return f"expired {len(expired)}, resumed {resumed}"
