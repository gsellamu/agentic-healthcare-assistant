"""FAISS-backed vector store for citable patient/medical documents.

IndexFlatIP over L2-normalized vectors (inner product == cosine similarity).
Each vector is paired with a Document carrying text + citation, so retrieval
results can be cited by the summarizer and checked by the grounding guardrail.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

import numpy as np

from hcasst.rag.embeddings import Embedder, get_embedder


class Document(BaseModel):
    text: str
    citation: str = ""          # e.g. "[E1]" or "[MedlinePlus]"
    source: str = ""
    metadata: dict = Field(default_factory=dict)


class Retrieved(BaseModel):
    document: Document
    score: float


class VectorStore:
    def __init__(self, embedder: Embedder | None = None) -> None:
        self.embedder = embedder or get_embedder()
        self.dim = self.embedder.dim
        self._docs: list[Document] = []
        self._index = self._new_index()

    def _new_index(self):
        import faiss
        return faiss.IndexFlatIP(self.dim)

    def __len__(self) -> int:
        return len(self._docs)

    def add(self, documents: list[Document]) -> None:
        if not documents:
            return
        vecs = self.embedder.embed([d.text for d in documents])
        self._index.add(np.asarray(vecs, dtype="float32"))
        self._docs.extend(documents)

    def query(self, text: str, k: int = 4) -> list[Retrieved]:
        if not self._docs:
            return []
        q = np.asarray([self.embedder.embed_one(text)], dtype="float32")
        k = min(k, len(self._docs))
        scores, idxs = self._index.search(q, k)
        out: list[Retrieved] = []
        for score, idx in zip(scores[0], idxs[0]):
            if idx == -1:
                continue
            out.append(Retrieved(document=self._docs[int(idx)], score=float(score)))
        return out


        