"""
Celery tasks for AI chat generation.

generate_ai_response:
  1. Loads conversation history from DB
  2. Calls AI provider (Anthropic or OpenAI) via httpx streaming
  3. Publishes each text chunk to Centrifugo channel: topic:{topic_id}
  4. Saves completed message to DB and publishes a "done" event

Centrifugo event shapes:
  {"type": "token",  "message_id": "...", "content": "partial text"}
  {"type": "done",   "message_id": "...", "content": "full text"}
  {"type": "error",  "message_id": "...", "content": "error message"}
"""
from __future__ import annotations

import json
import logging

import httpx
from celery import shared_task
from django.conf import settings

from . import services as svc

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Centrifugo helper
# ---------------------------------------------------------------------------

def _centrifugo_publish(channel: str, data: dict) -> None:
    """Fire-and-forget publish to Centrifugo HTTP API."""
    api_url = getattr(settings, "CENTRIFUGO_API_URL", "")
    api_key = getattr(settings, "CENTRIFUGO_API_KEY", "")
    if not api_url:
        return
    try:
        httpx.post(
            api_url,
            json={"method": "publish", "params": {"channel": channel, "data": data}},
            headers={"Authorization": f"apikey {api_key}", "Content-Type": "application/json"},
            timeout=5,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[centrifugo] publish failed channel=%s: %s", channel, exc)


# ---------------------------------------------------------------------------
# AI provider helpers
# ---------------------------------------------------------------------------

def _call_anthropic_streaming(messages: list[dict]) -> str:
    """Stream Anthropic and return the full response text."""
    api_key = getattr(settings, "ANTHROPIC_API_KEY", "")
    model = getattr(settings, "MODEL_NAME", "claude-haiku-4-5-20251001")

    # Normalise: Anthropic doesn't support "system" inside messages[]
    system_prompt = None
    clean_messages = []
    for m in messages:
        if m["role"] == "system":
            system_prompt = m["content"]
        else:
            clean_messages.append(m)

    payload: dict = {
        "model": model,
        "max_tokens": 4096,
        "stream": True,
        "messages": clean_messages,
    }
    if system_prompt:
        payload["system"] = system_prompt

    full_text = ""
    with httpx.stream(
        "POST",
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json=payload,
        timeout=120,
    ) as resp:
        resp.raise_for_status()
        for line in resp.iter_lines():
            if not line or not line.startswith("data:"):
                continue
            raw = line[len("data:"):].strip()
            if raw == "[DONE]":
                break
            try:
                evt = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if evt.get("type") == "content_block_delta":
                delta = evt.get("delta", {})
                if delta.get("type") == "text_delta":
                    full_text += delta.get("text", "")

    return full_text


def _call_anthropic_streaming_yield(messages: list[dict]):
    """Yield text chunks from Anthropic streaming (generator)."""
    api_key = getattr(settings, "ANTHROPIC_API_KEY", "")
    model = getattr(settings, "MODEL_NAME", "claude-haiku-4-5-20251001")

    system_prompt = None
    clean_messages = []
    for m in messages:
        if m["role"] == "system":
            system_prompt = m["content"]
        else:
            clean_messages.append(m)

    payload: dict = {
        "model": model,
        "max_tokens": 4096,
        "stream": True,
        "messages": clean_messages,
    }
    if system_prompt:
        payload["system"] = system_prompt

    with httpx.stream(
        "POST",
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json=payload,
        timeout=120,
    ) as resp:
        resp.raise_for_status()
        for line in resp.iter_lines():
            if not line or not line.startswith("data:"):
                continue
            raw = line[len("data:"):].strip()
            if raw == "[DONE]":
                break
            try:
                evt = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if evt.get("type") == "content_block_delta":
                delta = evt.get("delta", {})
                if delta.get("type") == "text_delta":
                    chunk = delta.get("text", "")
                    if chunk:
                        yield chunk


def _call_openai_streaming_yield(messages: list[dict]):
    """Yield text chunks from OpenAI streaming (generator)."""
    api_key = getattr(settings, "OPENAI_API_KEY", "")
    model = getattr(settings, "MODEL_NAME", "gpt-4o-mini")

    with httpx.stream(
        "POST",
        "https://api.openai.com/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "content-type": "application/json",
        },
        json={"model": model, "stream": True, "messages": messages},
        timeout=120,
    ) as resp:
        resp.raise_for_status()
        for line in resp.iter_lines():
            if not line or not line.startswith("data:"):
                continue
            raw = line[len("data:"):].strip()
            if raw == "[DONE]":
                break
            try:
                evt = json.loads(raw)
            except json.JSONDecodeError:
                continue
            delta = evt.get("choices", [{}])[0].get("delta", {})
            chunk = delta.get("content", "")
            if chunk:
                yield chunk


# ---------------------------------------------------------------------------
# Main Celery task
# ---------------------------------------------------------------------------

@shared_task(bind=True, queue="neuralops", name="chat.tasks.generate_ai_response")
def generate_ai_response(self, topic_id: str, ai_message_id: str) -> str:
    """
    Generate an AI response for the given topic and stream tokens to Centrifugo.

    Args:
        topic_id:      UUID of the ChatTopic
        ai_message_id: UUID of the placeholder ChatMessage (status=PENDING)

    Returns:
        "completed" | "failed"
    """
    from nucleus.models import ChatMessage

    logger.info(
        "[chat] generate_ai_response started topic=%s ai_message=%s",
        topic_id, ai_message_id,
    )

    channel = f"topic:{topic_id}"
    provider = getattr(settings, "AI_PROVIDER", "anthropic").lower()

    # ------------------------------------------------------------------ #
    # 1. Load conversation history                                         #
    # ------------------------------------------------------------------ #
    history = svc.list_messages(topic_id, limit=20)
    if not history:
        logger.warning("[chat] no history found for topic=%s", topic_id)
        _fail_message(ai_message_id, "No conversation history found.")
        _centrifugo_publish(channel, {
            "type": "error",
            "message_id": ai_message_id,
            "content": "No conversation history found.",
        })
        return "failed"

    # ------------------------------------------------------------------ #
    # 2. Mark message as STREAMING                                         #
    # ------------------------------------------------------------------ #
    ChatMessage.objects.filter(id=ai_message_id).update(status=ChatMessage.Status.STREAMING)

    # ------------------------------------------------------------------ #
    # 3. Stream AI response and publish tokens                             #
    # ------------------------------------------------------------------ #
    full_text = ""
    chunk_buffer = ""
    chunk_count = 0

    try:
        if provider == "anthropic":
            generator = _call_anthropic_streaming_yield(history)
        else:
            generator = _call_openai_streaming_yield(history)

        for chunk in generator:
            full_text += chunk
            chunk_buffer += chunk
            chunk_count += 1

            # Publish every 5 tokens to reduce HTTP overhead
            if chunk_count % 5 == 0:
                _centrifugo_publish(channel, {
                    "type": "token",
                    "message_id": ai_message_id,
                    "content": chunk_buffer,
                })
                chunk_buffer = ""

        # Flush remaining buffer
        if chunk_buffer:
            _centrifugo_publish(channel, {
                "type": "token",
                "message_id": ai_message_id,
                "content": chunk_buffer,
            })

    except httpx.HTTPStatusError as exc:
        logger.error(
            "[chat] AI HTTP error %s: %s",
            exc.response.status_code,
            exc.response.text[:200],
        )
        _fail_message(ai_message_id, f"AI service error: {exc.response.status_code}")
        _centrifugo_publish(channel, {
            "type": "error",
            "message_id": ai_message_id,
            "content": "AI service returned an error. Please try again.",
        })
        return "failed"

    except Exception as exc:  # noqa: BLE001
        logger.exception("[chat] AI call failed: %s", exc)
        _fail_message(ai_message_id, str(exc))
        _centrifugo_publish(channel, {
            "type": "error",
            "message_id": ai_message_id,
            "content": "AI generation failed. Please try again.",
        })
        return "failed"

    # ------------------------------------------------------------------ #
    # 4. Save completed message and publish "done"                         #
    # ------------------------------------------------------------------ #
    ChatMessage.objects.filter(id=ai_message_id).update(
        content=full_text,
        status=ChatMessage.Status.COMPLETED,
    )

    _centrifugo_publish(channel, {
        "type": "done",
        "message_id": ai_message_id,
        "content": full_text,
    })

    logger.info(
        "[chat] generate_ai_response completed topic=%s ai_message=%s tokens=%d",
        topic_id, ai_message_id, len(full_text),
    )
    return "completed"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _fail_message(ai_message_id: str, reason: str) -> None:
    from nucleus.models import ChatMessage

    ChatMessage.objects.filter(id=ai_message_id).update(
        status=ChatMessage.Status.FAILED,
        metadata={"role": "assistant", "error": reason},
    )
