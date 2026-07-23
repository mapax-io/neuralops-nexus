"""
Cosine similarity intent classifier for output type detection.

Uses the existing FastEmbed embedder (lazy-loaded on first call).
Pre-embeds example prompts per output type and caches the centroids.

Usage:
    from apps.output_types.classifier import classify_output_type
    output_type = await classify_output_type("show me a pie chart of sales")
    # → "chart"
"""
from __future__ import annotations

import logging

import numpy as np

log = logging.getLogger(__name__)

_embedder = None
_centroids: dict[str, np.ndarray] | None = None  # type_name → mean embedding vec


def _get_embedder():
    global _embedder
    if _embedder is None:
        from apps.factories.embedding import EmbeddingFactory
        _embedder = EmbeddingFactory.get()
    return _embedder


async def _build_centroids() -> dict[str, np.ndarray]:
    """Embed example prompts for each output type and compute centroids."""
    global _centroids
    if _centroids is not None:
        return _centroids

    from apps.output_types.registry import OutputTypeRegistry

    embedder = _get_embedder()
    result: dict[str, np.ndarray] = {}

    for spec in OutputTypeRegistry.all():
        if not spec.example_prompts:
            continue
        try:
            vecs = await embedder.embed(spec.example_prompts)
            arr = np.array(vecs, dtype=np.float32)
            result[spec.name] = arr.mean(axis=0)
        except Exception as exc:
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
    Returns the best-matching output type name for the prompt.

    Falls back to "text" if:
    - Classification fails for any reason
    - The winning non-text type doesn't score at least `threshold` above "text"
    """
    try:
        embedder = _get_embedder()
        centroids = await _build_centroids()

        if not centroids:
            return "text"

        query_vec = np.array((await embedder.embed([prompt]))[0], dtype=np.float32)

        scores: dict[str, float] = {
            name: _cosine(query_vec, centroid)
            for name, centroid in centroids.items()
        }

        text_score = scores.get("text", 0.0)
        best_type = max(scores, key=lambda k: scores[k])
        best_score = scores[best_type]

        if best_type != "text" and (best_score - text_score) < threshold:
            best_type = "text"

        log.debug(
            "[classifier] %r → %s (%.3f) text=%.3f",
            prompt[:60], best_type, best_score, text_score,
        )
        return best_type

    except Exception as exc:
        log.warning("[classifier] failed for prompt %r: %s", prompt[:60], exc)
        return "text"
