"""
Embedder — who turns text into vectors (Layer 3 decision 3).

The embedder is a PROJECT setting; unset = the system default, the LOCAL one
(owner's ruling, Open (a) resolved 2026-10-13). Vectors from different models
are never compared — the per-model schema (decision 7) enforces that at the
storage level, this module only answers "give me the embedder for this spec".

Providers:
  fastembed (default)  — local ONNX models, no network after the model is cached
  openai_compatible    — a remote /v1/embeddings endpoint; the CALLER bills it
                         under kind=remote_embedder (usage is nucleus's ledger)
  hash                 — deterministic, dependency-free; for tests and dev
                         stacks that must not download models. Documented here
                         on purpose: it is a real provider, not a test hook.
"""
from __future__ import annotations

import hashlib
import math
from abc import ABC, abstractmethod
from typing import Sequence

DEFAULT_EMBEDDER = {"provider": "fastembed", "model_id": "nomic-ai/nomic-embed-text-v1.5"}


class Embedder(ABC):
    @abstractmethod
    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...

    @abstractmethod
    def model_id(self) -> str:
        """The identity vectors are stamped with — two embedders with the same
        model_id MUST produce comparable vectors."""


class LocalEmbedder(Embedder):
    """fastembed — the default. The model object is cached per model_id for the
    process (loading it is the expensive part, ~seconds)."""

    _cache: dict[str, object] = {}

    def __init__(self, model_id: str) -> None:
        self._model_id = model_id

    def _model(self):
        if self._model_id not in self._cache:
            from fastembed import TextEmbedding  # lazy: pulls onnxruntime
            self._cache[self._model_id] = TextEmbedding(self._model_id)
        return self._cache[self._model_id]

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [list(map(float, v)) for v in self._model().embed(list(texts))]

    def model_id(self) -> str:
        return self._model_id


class RemoteEmbedder(Embedder):
    """An OpenAI-compatible /v1/embeddings endpoint. Synchronous on purpose —
    the store runs in a worker thread (asyncio.to_thread), same as txtai."""

    def __init__(self, model_id: str, api_base: str, api_key: str | None = None,
                 timeout: float = 30.0) -> None:
        self._model_id = model_id
        self._api_base = api_base.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        import httpx  # pinned dep
        headers = {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}
        response = httpx.post(
            f"{self._api_base}/embeddings",
            json={"model": self._model_id, "input": list(texts)},
            headers=headers, timeout=self._timeout,
        )
        response.raise_for_status()
        data = sorted(response.json()["data"], key=lambda d: d["index"])
        return [list(map(float, d["embedding"])) for d in data]

    def model_id(self) -> str:
        return self._model_id


class HashEmbedder(Embedder):
    """Deterministic token-hash vectors: similarity = token overlap. No
    downloads, no dependencies — tests and dev stacks. Dimensions come from
    the model id ("hash-384" → 384), so per-model-dimension behaviour
    (trial C4) is exercisable without real models."""

    def __init__(self, model_id: str = "hash-768") -> None:
        self._model_id = model_id
        try:
            self._dims = max(int(model_id.rsplit("-", 1)[-1]), 8)
        except ValueError:
            self._dims = 768

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._one(t) for t in texts]

    def _one(self, text: str) -> list[float]:
        vec = [0.0] * self._dims
        for token in text.lower().split():
            h = int(hashlib.md5(token.encode()).hexdigest(), 16)
            for k in range(8):
                vec[(h >> (k * 8)) % self._dims] += 1.0
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        return [x / norm for x in vec]

    def model_id(self) -> str:
        return self._model_id


class EmbedderFactory:
    """spec → Embedder. The spec is what nucleus sends on the embed endpoints
    (the project's setting), or None for the system default."""

    @staticmethod
    def build(spec: dict | None) -> Embedder:
        spec = spec or DEFAULT_EMBEDDER
        provider = (spec.get("provider") or "fastembed").lower()
        model_id = spec.get("model_id") or DEFAULT_EMBEDDER["model_id"]
        if provider == "fastembed":
            return LocalEmbedder(model_id)
        if provider in ("openai", "openai_compatible", "remote"):
            if not spec.get("api_base"):
                raise ValueError("a remote embedder needs api_base")
            return RemoteEmbedder(model_id, spec["api_base"], spec.get("api_key"))
        if provider == "hash":
            return HashEmbedder("hash-768" if model_id == DEFAULT_EMBEDDER["model_id"] else model_id)
        raise ValueError(f"unknown embedder provider: {provider!r}")

    @staticmethod
    def for_model(model_id: str) -> Embedder:
        """Rebuild the embedder an index was created with (search, reconnects,
        re-embeds): hash-* → HashEmbedder, anything else → fastembed. A REMOTE
        index's searches need the full spec, which the registry stores — the
        store passes that through build() instead of this shortcut."""
        if model_id.startswith("hash"):
            return HashEmbedder(model_id)
        return LocalEmbedder(model_id)
