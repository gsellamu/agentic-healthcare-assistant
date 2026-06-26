"""Turn patient history and search results into citable RAG documents.

Each evidence item becomes one Document keyed by its citation id, so anything
the summarizer retrieves can be cited and verified. Records are small, so we
index per-item rather than chunking.
"""

from __future__ import annotations

from hcasst.models import PatientHistory, SearchResult
from hcasst.rag.vectorstore import Document, VectorStore


def history_to_documents(history: PatientHistory) -> list[Document]:
    return [
        Document(
            text=item.text + (f" ({item.date})" if item.date else ""),
            citation=f"[{item.evidence_id}]",
            source=str(item.source),
            metadata={"evidence_id": item.evidence_id, "kind": str(item.kind),
                      "date": item.date, "patient_id": history.patient.id},
        )
        for item in history.items
    ]


def search_results_to_documents(results: list[SearchResult]) -> list[Document]:
    return [
        Document(text=f"{r.title}. {r.snippet}", citation=r.citation,
                 source=r.source, metadata={"url": r.url, "title": r.title})
        for r in results
    ]


def build_patient_index(history: PatientHistory,
                        extra: list[SearchResult] | None = None) -> VectorStore:
    store = VectorStore()
    docs = history_to_documents(history)
    if extra:
        docs += search_results_to_documents(extra)
    store.add(docs)
    return store

