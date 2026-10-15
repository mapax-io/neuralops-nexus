"""
Preflight plans + tool approvals (Step 2 split, docs/NUCLEUS-REVAMP.md).

What changed from the old services.py:
  - Tool approvals are no longer answers to a POLL. The new engine PAUSES:
    it POSTs its run state to /internal/messages/{msg}/pause/ and ends the
    stream with message_paused. Decisions land on that PausedRun row, and
    when EVERY pending call is decided (approvals decided, questions
    answered — the engine requires a result per deferred call), nucleus
    re-sends the original trigger job with a `resume` block.
  - approval_state() (the old poll) is gone with the polling worker.
  - Preflight plans are unchanged: a plan is a COMPLETED reply with a card,
    decided here, and an approval re-triggers a fresh run.

Pending records also mirror onto the reply row's metadata (approvals /
questions lists) so history shows the cards without reading PausedRun.
"""
from __future__ import annotations

import json
import logging
import uuid

from asgiref.sync import sync_to_async
from django.db import transaction
from django.utils import timezone

from authn.permissions.checker import PermissionChecker

from .events import preflight_decided_event, tool_approval_decided_event
from .realtime import publish_async, topic_channel

logger = logging.getLogger(__name__)

APPROVALS_MAX = 20
APPROVAL_PREVIEW_CHARS = 300
PLAN_MAX_STEPS = 12


# ── Preflight plans ───────────────────────────────────────────────────────────

def parse_plan(content: str) -> dict | None:
    """The plan a preflight reply carries, or None when the content is not one."""
    try:
        raw = json.loads(content)
    except (TypeError, ValueError):
        return None
    if not isinstance(raw, dict) or not isinstance(raw.get("steps"), list):
        return None
    steps = []
    for step in raw["steps"][:PLAN_MAX_STEPS]:
        if not isinstance(step, dict) or not str(step.get("title", "")).strip():
            continue
        tools = step.get("tools") if isinstance(step.get("tools"), list) else []
        steps.append({"title": str(step["title"]).strip(), "tools": [str(t) for t in tools], "writes": bool(step.get("writes"))})
    risks = [str(r) for r in raw["risks"]] if isinstance(raw.get("risks"), list) else []
    return {"summary": str(raw.get("summary") or "").strip(), "steps": steps, "risks": risks}


def plan_text(plan: dict) -> str:
    """The approved plan as the worker puts it ahead of the persona prompt."""
    lines = [plan["summary"]] if plan.get("summary") else []
    for i, step in enumerate(plan.get("steps", []), 1):
        detail = ", ".join(step.get("tools") or [])
        lines.append(f"{i}. {step['title']}" + (f" (tools: {detail})" if detail else "") + (" (writes)" if step.get("writes") else ""))
    return "\n".join(lines)


class PreflightError(Exception):
    """A decision that cannot be applied; `status` is the HTTP answer."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


class ApprovalError(Exception):
    """A decision that cannot be applied; `status` is the HTTP answer."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def _message_in_topic(topic, message_id):
    """The row for a message id in this topic, or None -- also for an id that is not a UUID (a scheduled fire's)."""
    from nucleus.models import ChatMessage
    try:
        uuid.UUID(str(message_id))
    except (ValueError, TypeError):
        return None
    return ChatMessage.objects.select_related("sender").filter(id=message_id, topic=topic).first()


def _claim_preflight(message_id, fields: dict) -> dict | None:
    """
    Move a proposal from proposed to decided, exactly once. None when someone
    got there first. The guard has to be part of the write — a double-click
    used to mean two runs from one approval (audit, 2026-09-21).
    """
    from nucleus.models import ChatMessage

    with transaction.atomic():
        row = ChatMessage.objects.select_for_update().filter(id=message_id).first()
        if not row:
            return None
        metadata = dict(row.metadata or {})
        preflight = dict(metadata.get("preflight") or {})
        if preflight.get("status") != "proposed":
            return None
        preflight.update(fields)
        metadata["preflight"] = preflight
        ChatMessage.objects.filter(id=row.id).update(metadata=metadata)
        return preflight


async def decide_preflight(*, topic, message_id: str, user, decision: str, note: str | None = None) -> dict:
    """
    Approve, adjust or decline a persona's proposal. Approve runs the plan with
    the tools back on; adjust asks for another plan with the note; decline ends
    it with a line in the topic. Once decided, a proposal stays decided.
    """
    import asyncio

    from nucleus.models import ChatMessage, Persona

    if decision not in ("approve", "adjust", "decline"):
        raise PreflightError(400, "Decision must be approve, adjust or decline.")
    msg = await sync_to_async(lambda: ChatMessage.objects.select_related("project", "company").filter(id=message_id, topic=topic).first())()
    if not msg:
        raise PreflightError(404, "Message not found.")
    preflight = dict((msg.metadata or {}).get("preflight") or {})
    if preflight.get("status") != "proposed":
        raise PreflightError(409, "This plan has already been decided." if preflight else "This message carries no plan to decide.")
    if not await sync_to_async(PermissionChecker.can)(user, "persona.approve_run", obj=topic):
        raise PreflightError(403, "You don't have permission to decide a persona's plan here.")
    persona = await sync_to_async(lambda: Persona.objects.filter(id=(msg.metadata or {}).get("persona_id"), is_active=True).first())()
    if not persona:
        raise PreflightError(409, "The persona behind this plan is gone.")
    if decision == "adjust" and not (note or "").strip():
        raise PreflightError(400, "Say what to change.")

    status = {"approve": "approved", "adjust": "adjusted", "decline": "declined"}[decision]
    claimed = await sync_to_async(_claim_preflight)(msg.id, {
        "status": status,
        "decided_by_id": str(user.id),
        "decided_by_name": user.get_display_name(),
        "decided_at": timezone.now().isoformat(),
        "note": (note or "").strip() or None,
    })
    if claimed is None:
        raise PreflightError(409, "This plan has already been decided.")
    preflight = claimed
    channel = topic_channel(str(topic.id))
    await publish_async(channel, preflight_decided_event(str(msg.id), preflight))

    # Lazy import: relay imports this module (record_approval_request).
    from .relay import trigger_ai_response_async
    from .messages import save_system_message

    # The run is the asker's (W22): the sender of the message that asked, or the
    # decider when that message cannot be found.
    asked = await sync_to_async(_message_in_topic)(topic, preflight.get("user_message_id"))
    common = dict(company=msg.company, project=msg.project, topic=topic, persona=persona, topic_id=str(topic.id),
                  user_message_id=preflight.get("user_message_id") or "", output_type="auto",
                  triggered_by=(asked.sender if asked and asked.sender else user))
    if decision == "approve":
        asyncio.create_task(trigger_ai_response_async(user_message=preflight.get("user_message") or "", approved_plan=plan_text(preflight["plan"]), **common))
    elif decision == "adjust":
        asyncio.create_task(trigger_ai_response_async(user_message=note.strip(), **common))
    else:
        line = await sync_to_async(save_system_message)(msg.company, msg.project, topic, f"@{persona.name}'s plan was declined by {user.get_display_name()}.")
        await publish_async(channel, line)
    return {"status": status, "preflight": preflight}


# ── Tool approvals + questions (pause-and-resume) ─────────────────────────────

def approval_record(approval: dict) -> dict | None:
    """The row's record for a worker approval_requested payload; None when it names no call."""
    call_id = (approval.get("call_id") or "").strip()
    tool = (approval.get("tool") or "").strip()
    if not call_id or not tool:
        return None
    return {
        "call_id": call_id,
        "tool": tool,
        "capability_id": (approval.get("capability_id") or "").strip(),
        "args_preview": (approval.get("args_preview") or "")[:APPROVAL_PREVIEW_CHARS],
        "status": "pending",
        "requested_at": timezone.now().isoformat(),
    }


def record_approval_request(message_id: str, approval: dict) -> dict | None:
    """Store a pending approval on the reply row NOW, mid-run, so history shows the card."""
    from nucleus.models import ChatMessage
    record = approval_record(approval)
    if not record:
        return None
    with transaction.atomic():
        msg = ChatMessage.objects.select_for_update().filter(id=message_id).first()
        if not msg:
            return None
        metadata = dict(msg.metadata or {})
        approvals = [a for a in (metadata.get("approvals") or []) if a.get("call_id") != record["call_id"]]
        approvals.append(record)
        metadata["approvals"] = approvals[-APPROVALS_MAX:]
        ChatMessage.objects.filter(id=message_id).update(metadata=metadata)
    return record


def record_question(message_id: str, question: dict) -> dict | None:
    """Store a pending question (item 5) on the reply row, same shape idea as approvals."""
    from nucleus.models import ChatMessage
    call_id = (question.get("call_id") or "").strip()
    text = (question.get("question") or "").strip()
    if not call_id or not text:
        return None
    record = {
        "call_id": call_id,
        "question": text,
        "options": [str(o) for o in (question.get("options") or [])],
        "status": "pending",
        "requested_at": timezone.now().isoformat(),
    }
    with transaction.atomic():
        msg = ChatMessage.objects.select_for_update().filter(id=message_id).first()
        if not msg:
            return None
        metadata = dict(msg.metadata or {})
        questions = [q for q in (metadata.get("questions") or []) if q.get("call_id") != call_id]
        questions.append(record)
        metadata["questions"] = questions[-APPROVALS_MAX:]
        ChatMessage.objects.filter(id=message_id).update(metadata=metadata)
    return record


def expire_open_approvals(metadata: dict) -> None:
    """A reply that ended leaves no card waiting: pending becomes expired, decisions stay."""
    for key in ("approvals", "questions"):
        records = metadata.get(key)
        if records:
            metadata[key] = [{**r, "status": "expired"} if r.get("status") == "pending" else r for r in records]


def _claim_card(message_id, key: str, call_id: str, fields: dict) -> dict | None:
    """
    Move one card (approval or question) from pending to decided, exactly once,
    against the row as it is at that moment.
    """
    from nucleus.models import ChatMessage

    with transaction.atomic():
        row = ChatMessage.objects.select_for_update().filter(id=message_id).first()
        if not row:
            return None
        metadata = dict(row.metadata or {})
        records = [dict(a) for a in (metadata.get(key) or [])]
        record = next((a for a in records if a.get("call_id") == call_id), None)
        if not record or record.get("status") != "pending":
            return None
        record.update(fields)
        metadata[key] = records
        ChatMessage.objects.filter(id=row.id).update(metadata=metadata)
        return record


def _claim_run_decision(message_id: str, call_id: str, decision: dict) -> tuple[object, bool] | None:
    """
    Write one decision onto the PausedRun row, exactly once per call, under the
    row lock. Returns (run, all_decided) or None when there is nothing to
    decide (no paused run, unknown call, or already decided).
    """
    from nucleus.models import PausedRun

    with transaction.atomic():
        run = PausedRun.objects.select_for_update().filter(message_id=message_id).first()
        if not run:
            return None
        pending_ids = {p.get("call_id") for p in (run.pending or [])}
        if call_id not in pending_ids:
            return None
        decisions = dict(run.decisions or {})
        if call_id in decisions:
            return None
        decisions[call_id] = decision
        run.decisions = decisions
        run.save(update_fields=["decisions"])
        return run, pending_ids <= set(decisions)


async def decide_tool_approval(*, topic, message_id: str, call_id: str, user, decision: str, always: bool = False) -> dict:
    """
    Allow or deny a held tool call, under persona.approve_run at the topic.
    `always` also writes "<capability>/<tool>": "auto" onto the persona (needs
    persona.update on the project too). Once decided, a call stays decided.
    When every pending call of the paused run is decided, the run RESUMES.
    """
    from nucleus.models import ChatMessage, PausedRun, Persona

    if decision not in ("allow", "deny"):
        raise ApprovalError(400, "Decision must be allow or deny.")
    msg = await sync_to_async(lambda: ChatMessage.objects.select_related("project").filter(id=message_id, topic=topic).first())()
    if not msg:
        raise ApprovalError(404, "Message not found.")
    run = await sync_to_async(lambda: PausedRun.objects.filter(message_id=message_id).first())()
    if not run:
        raise ApprovalError(409, "Nothing is waiting on this message.")
    item = next((p for p in (run.pending or []) if p.get("call_id") == call_id), None)
    if not item:
        raise ApprovalError(404, "This message holds no such tool call.")
    if item.get("kind", "approval") != "approval":
        raise ApprovalError(400, "This call is a question — it takes an answer, not an approval.")
    if call_id in (run.decisions or {}):
        raise ApprovalError(409, "This call has already been decided.")
    if not await sync_to_async(PermissionChecker.can)(user, "persona.approve_run", obj=topic):
        raise ApprovalError(403, "You don't have permission to decide a persona's tool calls here.")
    if always and not await sync_to_async(PermissionChecker.can)(user, "persona.update", obj=msg.project):
        raise ApprovalError(403, "Allowing a tool always changes the persona, which needs the right to edit personas.")

    if always and decision == "allow":
        persona = await sync_to_async(lambda: Persona.objects.filter(id=(msg.metadata or {}).get("persona_id"), is_active=True).first())()
        if persona:
            levels = dict(persona.tool_levels or {})
            levels[f"{item.get('capability_id') or ''}/{item.get('tool')}"] = "auto"
            persona.tool_levels = levels
            await sync_to_async(persona.save)(update_fields=["tool_levels"])

    claim = await sync_to_async(_claim_run_decision)(message_id, call_id, {
        "kind": "approval",
        "decision": "allow" if decision == "allow" else "deny",
        "decided_by_id": str(user.id),
        "decided_by_name": user.get_display_name(),
        "decided_at": timezone.now().isoformat(),
    })
    if claim is None:
        raise ApprovalError(409, "This call has already been decided.")
    run, all_decided = claim

    # Mirror onto the message card so history shows the verdict.
    record = await sync_to_async(_claim_card)(message_id, "approvals", call_id, {
        "status": "allowed" if decision == "allow" else "denied",
        "always": bool(always and decision == "allow"),
        "decided_by_id": str(user.id),
        "decided_by_name": user.get_display_name(),
        "decided_at": timezone.now().isoformat(),
    }) or {"call_id": call_id, "status": "allowed" if decision == "allow" else "denied"}
    await publish_async(topic_channel(str(topic.id)), tool_approval_decided_event(str(msg.id), record))

    if all_decided:
        from .relay import resume_paused_run
        import asyncio
        asyncio.create_task(resume_paused_run(message_id))
    return {"status": record["status"], "approval": record, "resumed": bool(all_decided)}


async def answer_question(*, topic, message_id: str, call_id: str, user, answer: str) -> dict:
    """
    Answer a persona's question (item 5). Only the person who started the run
    answers (W22 — the reply is theirs). When every pending call is decided,
    the run resumes with the answer as that call's tool result.
    """
    from nucleus.models import ChatMessage, PausedRun

    answer = (answer or "").strip()
    if not answer:
        raise ApprovalError(400, "Say an answer.")
    msg = await sync_to_async(lambda: ChatMessage.objects.filter(id=message_id, topic=topic).first())()
    if not msg:
        raise ApprovalError(404, "Message not found.")
    owner_id = (msg.metadata or {}).get("triggered_by_id")
    if owner_id and owner_id != str(user.id):
        raise ApprovalError(403, "Only the person who called the persona answers its questions.")
    run = await sync_to_async(lambda: PausedRun.objects.filter(message_id=message_id).first())()
    if not run:
        raise ApprovalError(409, "Nothing is waiting on this message.")
    item = next((p for p in (run.pending or []) if p.get("call_id") == call_id), None)
    if not item:
        raise ApprovalError(404, "This message holds no such question.")
    if item.get("kind") != "question":
        raise ApprovalError(400, "This call is a tool approval, not a question.")
    if call_id in (run.decisions or {}):
        raise ApprovalError(409, "This question has already been answered.")

    claim = await sync_to_async(_claim_run_decision)(message_id, call_id, {
        "kind": "question",
        "answer": answer,
        "decided_by_id": str(user.id),
        "decided_by_name": user.get_display_name(),
        "decided_at": timezone.now().isoformat(),
    })
    if claim is None:
        raise ApprovalError(409, "This question has already been answered.")
    run, all_decided = claim

    record = await sync_to_async(_claim_card)(message_id, "questions", call_id, {
        "status": "answered",
        "answer": answer,
        "decided_by_id": str(user.id),
        "decided_by_name": user.get_display_name(),
        "decided_at": timezone.now().isoformat(),
    }) or {"call_id": call_id, "status": "answered", "answer": answer}
    await publish_async(topic_channel(str(topic.id)), {
        "type": "question_answered", "id": str(msg.id), "question": record,
    })

    if all_decided:
        from .relay import resume_paused_run
        import asyncio
        asyncio.create_task(resume_paused_run(message_id))
    return {"status": "answered", "question": record, "resumed": bool(all_decided)}
