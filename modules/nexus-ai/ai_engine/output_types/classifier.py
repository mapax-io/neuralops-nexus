"""
Cosine similarity intent classifier for output type detection (0.8.0, kept;
rewired onto ai_engine.vector_db's Embedder interface — the legacy
EmbeddingFactory is gone).

Pre-embeds example prompts per output type and caches the centroids. The
embedder comes from EngineSettings.classifier_embedder ("provider[:model]",
default fastembed's nomic model — the same local default the vector store
uses, so production pays for ONE cached model); tests inject their own via
set_embedder().
"""
from __future__ import annotations

import asyncio
import logging

import numpy as np

from ai_engine.vector_db.embedder import Embedder, EmbedderFactory
from ai_engine.output_types.registry import OutputTypeRegistry

log = logging.getLogger(__name__)

_embedder: Embedder | None = None
_centroids: dict[str, np.ndarray] | None = None  # type_name → mean embedding vec


def set_embedder(embedder: Embedder | None) -> None:
    """Swap the classifier's embedder (tests, config changes); drops centroids."""
    global _embedder, _centroids
    _embedder = embedder
    _centroids = None


def _get_embedder() -> Embedder:
    global _embedder
    if _embedder is None:
        from ai_engine.core.config import EngineSettings
        spec = EngineSettings().classifier_embedder
        provider, _, model_id = spec.partition(":")
        _embedder = EmbedderFactory.build(
            {"provider": provider, **({"model_id": model_id} if model_id else {})})
    return _embedder


async def _build_centroids() -> dict[str, np.ndarray]:
    """Embed example prompts for each output type and compute centroids."""
    global _centroids
    if _centroids is not None:
        return _centroids

    embedder = _get_embedder()
    result: dict[str, np.ndarray] = {}

    for spec in OutputTypeRegistry.all():
        if not spec.example_prompts:
            continue
        try:
            vecs = await asyncio.to_thread(embedder.embed, spec.example_prompts)
            arr = np.array(vecs, dtype=np.float32)
            result[spec.name] = arr.mean(axis=0)
        except Exception as exc:  # noqa: BLE001
            log.warning("[classifier] failed to embed prompts for type %s: %s", spec.name, exc)

    _centroids = result
    log.info("[classifier] built centroids for %d output types", len(result))
    return result


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    norm_a = float(np.linalg.norm(a))
    norm_b = float(np.linalg.norm(b))
    if norm_a < 1e-9 or norm_b < 1e-9:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


async def classify_output_type(prompt: str, threshold: float = 0.05) -> str:
    """
    The best-matching output type name for the prompt. Falls back to "text"
    when classification fails or the winner doesn't beat "text" by `threshold`
    (0.8.0's rule, kept — text is the safe default).
    """
    try:
        embedder = _get_embedder()
        centroids = await _build_centroids()
        if not centroids:
            return "text"

        query_vec = np.array((await asyncio.to_thread(embedder.embed, [prompt]))[0], dtype=np.float32)
        scores = {name: _cosine(query_vec, centroid) for name, centroid in centroids.items()}

        text_score = scores.get("text", 0.0)
        best_type = max(scores, key=lambda k: scores[k])
        if best_type != "text" and (scores[best_type] - text_score) < threshold:
            best_type = "text"

        log.debug("[classifier] %r → %s (%.3f) text=%.3f",
                  prompt[:60], best_type, scores[best_type], text_score)
        return best_type
    except Exception as exc:  # noqa: BLE001
        log.warning("[classifier] failed for prompt %r: %s", prompt[:60], exc)
        return "text"
