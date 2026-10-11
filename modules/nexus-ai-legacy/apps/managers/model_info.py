"""The one fact about a model the app needs beyond its name: how much context it takes."""
from __future__ import annotations

import logging

import litellm

logger = logging.getLogger(__name__)


def context_window_for(model_config) -> int | None:
    """Max input tokens per LiteLLM's model registry; None when it does not know (never a guess)."""
    try:
        info = litellm.get_model_info(model_config.model_id)
    except Exception as exc:
        logger.debug("[model_info] no registry entry for %s: %s", getattr(model_config, "model_id", "?"), exc)
        return None
    value = (info or {}).get("max_input_tokens") or (info or {}).get("max_tokens")
    return int(value) if value else None
