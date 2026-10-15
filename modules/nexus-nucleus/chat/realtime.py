"""
Centrifugo publish — the one door to the live channel (Step 2 split,
docs/NUCLEUS-REVAMP.md; moved verbatim from chat/services.py).

Publish failure is never the caller's problem: both functions log and
swallow, because losing a live event must never lose a saved message.
"""
from __future__ import annotations

import logging

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)


def publish(channel: str, data: dict) -> None:
    """
    Synchronous publish — kept for compatibility with sync views.
    Prefer publish_async() inside async endpoints.
    """
    api_url = getattr(settings, "CENTRIFUGO_API_URL", "")
    api_key = getattr(settings, "CENTRIFUGO_API_KEY", "")
    if not api_url:
        logger.warning("[centrifugo] CENTRIFUGO_API_URL not set — skipping publish")
        return
    try:
        httpx.post(
            f"{api_url}/publish",
            json={"channel": channel, "data": data},
            headers={
                "X-API-Key": api_key,
                "Content-Type": "application/json",
            },
            timeout=3,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[centrifugo] publish failed channel=%s: %s", channel, exc)


async def publish_async(channel: str, data: dict) -> None:
    """
    Async publish — use inside async Django Ninja endpoints.
    """
    api_url = getattr(settings, "CENTRIFUGO_API_URL", "")
    api_key = getattr(settings, "CENTRIFUGO_API_KEY", "")
    if not api_url:
        logger.warning("[centrifugo] CENTRIFUGO_API_URL not set — skipping publish")
        return
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{api_url}/publish",
                json={"channel": channel, "data": data},
                headers={
                    "X-API-Key": api_key,
                    "Content-Type": "application/json",
                },
                timeout=3,
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[centrifugo] publish_async failed channel=%s: %s", channel, exc)


def topic_channel(topic_id: str) -> str:
    """Returns the Centrifugo channel name for a topic."""
    return f"topic-{topic_id}"
