"""Long-term patient memory — persistent context across sessions.

Stores interaction context that is NOT in the medical record (preferences,
caregiver info, prior-session topics) in the durable SQLite `memory` table,
keyed by patient and scope. Recall is semantic: memories are indexed in FAISS
alongside the patient's evidence, so a query retrieves relevant context by
meaning.

This is the simple, spec-required memory module ("retain long-term context").
Adaptive consolidation (Mem0/Zep-style ADD/UPDATE/NOOP, supersede, recency
ranking) is fenced as the S3 stretch.
"""

from __future__ import annotations

from pydantic import BaseModel

from config.settings import Settings, get_settings
from hcasst.db.store import Store
from hcasst.models import PatientHistory
from hcasst.rag.ingest import build_patient_index
from hcasst.rag.vectorstore import Document, Retrieved, VectorStore


class RecalledContext(BaseModel):
    items: list[Retrieved]

    def as_evidence(self) -> str:
        return "\n".join(f"{r.document.citation} {r.document.text}" for r in self.items)


class MemoryManager:
    """Memory facade over SQLite (durable) + a per-patient FAISS index (recall)."""

    def __init__(self, settings: Settings | None = None, store: Store | None = None) -> None:
        self.settings = settings or get_settings()
        self.store = store or Store()
        self._indexes: dict[str, VectorStore] = {}

    # ── write (durable) ──────────────────────────────────────────────────
    def remember(self, patient_id: str, content: str, kind: str = "note",
                 scope: str = "patient", importance: float = 0.5) -> int | None:
        content = (content or "").strip()
        if not content:
            return None
        # S3: adaptive reconcile (ADD/UPDATE/NOOP) would go here; core always adds.
        mem_id = self.store.add_memory(patient_id, kind=kind, content=content,
                                       scope=scope, importance=importance)
        self._indexes.pop(patient_id, None)  # invalidate index so recall sees it
        return mem_id

    def long_term(self, patient_id: str, scope: str | None = None) -> list[dict]:
        return self.store.memories(patient_id, scope=scope, status="active")

    # ── recall (semantic) ────────────────────────────────────────────────
    def index_patient(self, history: PatientHistory) -> VectorStore:
        """Build a FAISS index over the patient's evidence + stored memories."""
        vs = build_patient_index(history)
        notes = self.store.memories(history.patient.id, status="active")
        if notes:
            vs.add([
                Document(text=n["content"], citation=f"[M{n['id']}]", source="memory",
                         metadata={"kind": n["kind"], "scope": n["scope"],
                                   "patient_id": history.patient.id})
                for n in notes
            ])
        self._indexes[history.patient.id] = vs
        return vs

    def recall(self, patient_id: str, query: str, k: int = 4) -> RecalledContext:
        vs = self._indexes.get(patient_id)
        if vs is None:
            return RecalledContext(items=[])
        return RecalledContext(items=vs.query(query, k=k))



        