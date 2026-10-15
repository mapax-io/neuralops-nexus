"""
chat/services.py — a thin re-export page (Step 2 split, docs/NUCLEUS-REVAMP.md).

The 1774-line original is split into small files, each with one job:

    chat/directives.py  — parse what the user typed (@mentions, @session, …)
    chat/realtime.py    — the one door to Centrifugo
    chat/messages.py    — message rows: save, update, list, serialise
    chat/approvals.py   — preflight plans + tool approvals + questions
    chat/nexus_ai.py    — NexusAIClient, the one class that talks to the engine
    chat/relay.py       — one reply's whole life, queue-per-topic

This module only re-exports their public names so existing imports
(`from chat.services import publish`, `chat_svc.save_system_message`, …)
keep working. New code should import from the real module.

Deleted in the split (owner's rulings, 2026-10-14):
    trigger_ai_swarm_response_async — the swarm road is gone
    approval_state                  — the old approvals poll; the new engine
                                      pauses and resumes instead
"""
from __future__ import annotations

# Parsing
from .directives import (  # noqa: F401
    MessageDirectives,
    extract_output_type,
    extract_routine,
    extract_session_directive,
)

# Live channel
from .realtime import publish, publish_async, topic_channel  # noqa: F401

# Message rows
from .messages import (  # noqa: F401
    ACTIVITY_TRAIL_MAX,
    ORPHAN_AFTER_SECONDS,
    USAGE_FIELDS,
    build_context_sources,
    close_session,
    create_ai_message,
    create_session,
    fail_ai_message,
    get_active_session,
    list_messages,
    reap_orphaned_replies,
    remember_tool_call,
    repost_untaken_nudges,
    request_nudge_for_message,
    request_stop_for_message,
    save_system_message,
    save_user_message,
    serialise,
    set_message_status,
    update_ai_message,
    usage_from,
    with_usage,
)

# Plans, approvals, questions
from .approvals import (  # noqa: F401
    APPROVAL_PREVIEW_CHARS,
    APPROVALS_MAX,
    PLAN_MAX_STEPS,
    ApprovalError,
    PreflightError,
    answer_question,
    approval_record,
    decide_preflight,
    decide_tool_approval,
    expire_open_approvals,
    parse_plan,
    plan_text,
    record_approval_request,
    record_question,
)

# The relay + the client
from .nexus_ai import NexusAIClient  # noqa: F401
from .relay import (  # noqa: F401
    end_stopped_reply,
    resume_paused_run,
    trigger_ai_response_async,
)

# Old private names, kept for existing callers and tests.
_serialise = serialise
_build_context_sources = build_context_sources


async def embed_message_async(**payload) -> None:
    """Old name and signature, kept: embed one message via the client."""
    await NexusAIClient().embed_message(payload)
