"""
Model fallbacks (W7): when the persona's model cannot answer -- its key
revoked, no credit left, rate-limited, the model id gone, the provider down
or unreachable -- the turn is retried on the next model of the persona's
ordered fallback list, and the reply says which model answered.

Only a failure that happens BEFORE anything reached the reader is retried:
once a delta or a tool call has been streamed, restarting would duplicate
what the reader already saw, so that failure is reported like any other. A
refusal, a bad request or a too-long conversation is the model answering,
not failing, and is never retried either (is_model_failure).

Nucleus's chat/reasons.py decides the WORDING the reader sees for a failure;
this module decides whether to RETRY. Two concerns, two (small) classifiers.
"""
from __future__ import annotations

import logging
import re
from collections.abc import AsyncIterator, Sequence
from typing import Any

from apps.schemas.trigger import AgentEvent, AgentEventType, ModelConfig, PersonaConfig

log = logging.getLogger(__name__)

# The error_code the runner puts on a message_error the fallback run may retry.
MODEL_FAILURE = "model_failure"

# HTTP statuses that mean the model could not be used, not that the request was wrong.
_FAILURE_STATUSES = {401, 402, 403, 404, 408, 409, 425, 429}
# Exception class names (litellm, pydantic-ai, httpx) for wrappers that carry no status.
_FAILURE_CLASSES = {
    "AuthenticationError", "PermissionDeniedError", "BudgetExceededError", "RateLimitError", "NotFoundError",
    "ServiceUnavailableError", "InternalServerError", "BadGatewayError", "APIConnectionError", "Timeout",
    "ModelAPIError", "ConnectError", "ReadTimeout", "ConnectTimeout", "RemoteProtocolError",
}
_ANSWER_CLASSES = {
    "ContentFilterError", "ContentPolicyViolationError", "ContextWindowExceededError", "BadRequestError",
    "UnprocessableEntityError", "UnexpectedModelBehavior", "UserError",
}
_BILLING_TEXT = re.compile(r"credit balance|insufficient_quota|insufficient credit|billing|no remaining|exceeded your current quota|payment required", re.I)
# "refused to"/"refusal" is the model declining; "connection refused" is not.
_ANSWER_TEXT = re.compile(r"context.?length|maximum context|too many tokens|token limit|content.?filter|content_policy|safety|\brefusal\b|refused to", re.I)
_FAILURE_TEXT = re.compile(
    r"\b(401|402|403|404|408|429|5\d\d)\b|rate.?limit|too many requests|insufficient_quota|exceeded your current quota"
    r"|invalid_api_key|incorrect api key|authentication|model_not_found|does not exist|timed? ?out|timeout"
    r"|connection (error|reset|refused|closed)|peer closed|unreachable|service unavailable|overloaded|internal server error|bad gateway",
    re.I,
)


def is_model_failure(exc: BaseException) -> bool:
    """True when the model could not be used at all -- the case another model may answer."""
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        if status in _FAILURE_STATUSES or status >= 500:
            return True
        # Some providers report an empty balance as a 400 (Anthropic: "Your
        # credit balance is too low"): the model is unusable all the same.
        return bool(_BILLING_TEXT.search(str(exc)))
    name = type(exc).__name__
    if name in _FAILURE_CLASSES:
        return True
    if name in _ANSWER_CLASSES:
        return False
    text = str(exc)
    if _ANSWER_TEXT.search(text):
        return False
    return bool(_FAILURE_TEXT.search(text))


# Events that mean the reader has seen something of this attempt.
_VISIBLE = {
    AgentEventType.DELTA.value, AgentEventType.TOOL_CALL_START.value, AgentEventType.TOOL_CALL_END.value,
    AgentEventType.APPROVAL_REQUESTED.value, AgentEventType.SWARM_TRANSITION.value,
}


class FallbackRun:
    """One turn over the persona's model and, when it fails before answering, its fallbacks in order."""

    def __init__(self, runner: Any, job: Any, messages: Sequence[Any], persona: PersonaConfig, tools: list[dict] | None = None):
        self.runner, self.job, self.messages, self.persona, self.tools = runner, job, messages, persona, tools
        # The model the reply came from; the primary until a fallback takes over.
        self.model: ModelConfig = persona.model
        self.fell_back = False

    @property
    def answered_by_model(self) -> str | None:
        """What message_done says: the fallback that answered, or None for the persona's own model."""
        return f"{self.model.name or self.model.model_id} (fallback)" if self.fell_back else None

    async def events(self) -> AsyncIterator[AgentEvent]:
        candidates = [self.persona.model, *self.persona.fallback_models]
        for index, candidate in enumerate(candidates):
            attempt = self.persona if index == 0 else self.persona.model_copy(update={"model": candidate})
            self.model, self.fell_back = candidate, index > 0
            last = index == len(candidates) - 1
            visible = False
            failed: AgentEvent | None = None
            stream = self.runner.run_stream(self.job, self.messages, attempt, tools=self.tools)
            async for event in stream:
                kind = event.type.value if isinstance(event.type, AgentEventType) else event.type
                if kind == AgentEventType.ERROR.value and event.error_code == MODEL_FAILURE and not visible and not last:
                    failed = event
                    break
                if kind in _VISIBLE:
                    visible = True
                yield event
            if failed is None:
                return
            await stream.aclose()
            log.warning(
                "[fallbacks] %s: %s failed before answering (%s); trying %s",
                self.persona.name, candidate.model_id, failed.error, candidates[index + 1].model_id,
            )
