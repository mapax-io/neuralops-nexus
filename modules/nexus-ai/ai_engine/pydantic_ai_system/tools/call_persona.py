"""
call_persona — item 46's one-shot delegation tool (Layer 6 decision 5,
trial I 3/3 on pinned 2.55.0: an executing FunctionToolset tool may run a
whole second engine loop inside itself, no deadlock, usages separate).

A persona whose nucleus row says `delegation_enabled` (typically the chain's
supervisor) gets this tool. Calling it runs ANOTHER persona of the same
project on a sub-task through the ENGINE'S OWN respond() — a fresh system, an
ordinary inner run — and returns that persona's finished reply as the tool
result. It ALWAYS returns (never hands the stream over).

Rules (the doc's delegation rules, enforced here):
  - the inner run is UNATTENDED (interactive=False): an inner ask-tool is
    refused with the worded text, never paused — a pause inside a pause has
    no stored shape; the outer persona decides what to do with the refusal;
  - depth limit 1: the inner job carries delegation_depth=1, and the toolset
    is only attached at depth 0 — a called persona cannot call further;
  - max calls per reply and a hard timeout per call (settings);
  - billing: the inner run posts its OWN usage records through its own
    respond() — recorded under the CALLEE's persona/model ids, with
    message_id "{outer_msg}:cp{n}" so the spend stays traceable to the
    message without colliding with it (vector row ids included).
"""
from __future__ import annotations

import asyncio
import logging

from pydantic_ai.toolsets import FunctionToolset

from ai_engine.core.config import EngineSettings
from fastapi_app.contracts.trigger import AgentEventType, TriggerJob

log = logging.getLogger(__name__)

DELEGATION_TOOLSET_ID = "delegation"
_REFUSED_MAX = ("call_persona refused: this reply already used its delegation "
                "budget ({max} calls). Finish with what you have.")
_TIMED_OUT = ("call_persona failed: persona {persona_id!r} did not finish "
              "within {seconds:.0f}s. Nothing was returned.")
_FAILED = "call_persona failed: persona {persona_id!r} ended with an error: {error}"
_EMPTY = "call_persona: persona {persona_id!r} returned no content."


def _handover_message(task: str, summary: str, references: list[str],
                      constraints: str, expected_output: str) -> str:
    """The Handover, rendered as the inner run's user message (small on
    purpose — context travels as references, never as pasted history)."""
    parts = [f"Task: {task.strip()}"]
    if summary.strip():
        parts.append(f"What is known so far: {summary.strip()}")
    if references:
        parts.append("Read first:\n" + "\n".join(f"- {r}" for r in references))
    if constraints.strip():
        parts.append(f"Constraints: {constraints.strip()}")
    if expected_output.strip():
        parts.append(f"Expected output: {expected_output.strip()}")
    return "\n\n".join(parts)


def call_persona_toolset(job: TriggerJob, settings: EngineSettings) -> FunctionToolset:
    """One toolset per reply — the call counter lives in the closure."""
    calls = {"n": 0}

    async def call_persona(persona_id: str, task: str, summary: str = "",
                           references: list[str] | None = None,
                           constraints: str = "", expected_output: str = "") -> str:
        """Run another persona of this project on one sub-task and return its
        finished reply. Hand over a small brief, not the conversation: name
        the task, what is known, which files or documents to read first, the
        constraints, and what the output should look like."""
        if calls["n"] >= settings.delegation_max_calls:
            return _REFUSED_MAX.format(max=settings.delegation_max_calls)
        index = calls["n"]
        calls["n"] += 1

        inner_job = TriggerJob(
            job_id=f"{job.job_id}:cp{index}",
            msg_id=f"{job.msg_id}:cp{index}",
            persona_id=persona_id,
            topic_id=job.topic_id,
            user_message_id=job.user_message_id,
            message=_handover_message(task, summary, references or [],
                                      constraints, expected_output),
            company_id=job.company_id,
            project_id=job.project_id,
            user_id=job.user_id,
            interactive=False,        # refuse ask-tools, never pause inside
            delegation_depth=1,       # depth limit: the callee cannot delegate
        )
        # a FRESH system per inner run — respond() holds per-run state, and the
        # outer run's generator must not be touched (same rule as the factory's)
        from ai_engine.core.ai_system import AISystemFactory
        system = AISystemFactory.create("pydantic_ai")

        content: str | None = None
        error: str | None = None
        try:
            async with asyncio.timeout(settings.delegation_timeout_seconds):
                async for event in system.respond(inner_job):
                    # drained silently: the outer run is mid-tool; item 19's
                    # tool_call_start/end already shows the delegation outside
                    if event.type is AgentEventType.END:
                        content = event.content or ""
                    elif event.type is AgentEventType.ERROR:
                        error = event.error or "unknown error"
        except TimeoutError:
            log.warning("[delegation] persona %s timed out for %s", persona_id, job.msg_id)
            return _TIMED_OUT.format(persona_id=persona_id,
                                     seconds=settings.delegation_timeout_seconds)
        except Exception as exc:  # noqa: BLE001 — a broken callee is the CALLER's tool result
            log.exception("[delegation] persona %s failed for %s", persona_id, job.msg_id)
            return _FAILED.format(persona_id=persona_id, error=str(exc)[:300])
        if error is not None:
            return _FAILED.format(persona_id=persona_id, error=error[:300])
        if content is None or not content.strip():
            return _EMPTY.format(persona_id=persona_id)
        return content

    return FunctionToolset([call_persona], id=DELEGATION_TOOLSET_ID)
