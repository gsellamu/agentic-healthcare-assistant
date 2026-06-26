"""Pluggable text embeddings.

HashingEmbedder: dependency-free, deterministic bag-of-words hashing into a
fixed-dim vector. Good enough for keyword-ish semantic retrieval over small
patient records, and it needs no model download or API key — so RAG runs fully
offline. Vectors are L2-normalized so inner product == cosine similarity
(matches FAISS IndexFlatIP).
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import Protocol

_TOKEN = re.compile(r"[a-z0-9]+")


class Embedder(Protocol):
    dim: int
    def embed(self, texts: list[str]) -> list[list[float]]: ...
    def embed_one(self, text: str) -> list[float]: ...


def _normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


class HashingEmbedder:
    """Deterministic hashing bag-of-words embedder (no external deps)."""

    def __init__(self, dim: int = 256) -> None:
        self.dim = dim

    def _vec(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for tok in _TOKEN.findall(text.lower()):
            h = int(hashlib.md5(tok.encode("utf-8")).hexdigest(), 16)
            idx = h % self.dim
            sign = 1.0 if (h >> 8) & 1 else -1.0
            vec[idx] += sign
        return _normalize(vec)

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]

    def embed_one(self, text: str) -> list[float]:
        return self._vec(text)
    
def get_embedder(settings=None) -> Embedder:
    """SentenceTransformer by default (course technique); hashing fallback."""
    from config.settings import get_settings
    settings = settings or get_settings()
    if settings.use_st_embeddings and not settings.offline:
        try:
            return SentenceTransformerEmbedder(settings.st_model)
        except Exception as exc:  # noqa: BLE001
            from hcasst.obs.logging import get_logger
            get_logger("embeddings").warning(
                "sentence-transformers unavailable (%s); using HashingEmbedder", exc
            )
    return HashingEmbedder()



class SentenceTransformerEmbedder:
    """Real semantic embeddings via sentence-transformers (course technique)."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        from sentence_transformers import SentenceTransformer
        self._model = SentenceTransformer(model_name)
        self.dim = self._model.get_embedding_dimension() 

    def embed(self, texts: list[str]) -> list[list[float]]:
        vecs = self._model.encode(texts, normalize_embeddings=True)
        return [list(map(float, v)) for v in vecs]

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]
    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]
    
    