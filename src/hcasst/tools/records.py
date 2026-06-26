# Medical Record Management services:
""" 
1. Add/Update medical records with vist notes/after visit summary 
    - structured/unstructured patient history
2. Retrive medical histories: 
    - Summarize past diagnoses, tretments, and relevant alerts using LLMs.

Core build loads patients from data/seed/*.json and keeps added notes in
memory. Retrieval returns a typed PatientHistory (citable EvidenceItems);
adding a note is a human-in-the-loop write (propose -> confirm), never silent.
(Live FHIR read/write is a stretch add-on with the same return types.)
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field

from config.settings import SEED_DIR, Settings, get_settings
from hcasst.models import EvidenceItem, EvidenceKind, Patient, PatientHistory


def _load_seed() -> list[PatientHistory]:
    path = Path(SEED_DIR) / "patients.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    histories: list[PatientHistory] = []
    for rec in data:
        patient = Patient(
            id=rec["id"], name=rec["name"],
            gender=rec.get("gender", ""), birth_date=rec.get("birth_date", ""),
            source="seed",
        )
        items = [
            EvidenceItem(
                evidence_id=f"E{i + 1}",
                kind=it["kind"],
                text=it["text"],
                date=it.get("date", ""),
                source="seed",
            )
            for i, it in enumerate(rec.get("items", []))
        ]
        histories.append(PatientHistory(patient=patient, items=items))
    return histories


class VisitNote(BaseModel):
    patient_id: str
    summary: str
    kind: EvidenceKind = Field(
        default=EvidenceKind.NOTE,
        description="Record type: condition|medication|encounter|observation|allergy|note",
    )
    author: str = "clinical-staff"
    status: str = "proposed"
    target_evidence_id: str = ""   # empty -> add new; set -> update existing


class RecordsManager:
    def __init__(self, settings: Settings | None = None, store=None) -> None:
        from hcasst.db.store import Store
        self.settings = settings or get_settings()
        self.store = store or Store()
        self._histories: dict[str, PatientHistory] = {
            h.patient.id: h for h in _load_seed()
        }
        if self.settings.load_instructor_data:
            try:
                from hcasst.tools.ingest_external import load_instructor_data
                for h in load_instructor_data():
                    self._histories[h.patient.id] = h
            except Exception as exc:  # noqa: BLE001
                from hcasst.obs.logging import get_logger
                get_logger("records").warning("instructor data load skipped: %s", exc)
        self._pending: dict[int, VisitNote] = {}
        self._next_id = 1

    # ── reads ────────────────────────────────────────────────────────────
    def list_patients(self) -> list[Patient]:
        return [h.patient for h in self._histories.values()]

    def get_patient_history(self, patient_id: str) -> PatientHistory:
        hist = self._histories.get(patient_id)
        if hist is None:
            raise ValueError(f"Unknown patient {patient_id}")
        return hist

    # ── HITL write ───────────────────────────────────────────────────────
    def propose_visit(self, patient_id: str, summary: str, *,
                      kind: EvidenceKind = EvidenceKind.NOTE,
                      target_evidence_id: str = "",
                      author: str = "clinical-staff") -> VisitNote:
        if patient_id not in self._histories:
            raise ValueError(f"Unknown patient {patient_id}")
        note = VisitNote(patient_id=patient_id, summary=summary, kind=kind,
                         author=author, target_evidence_id=target_evidence_id)
        nid = self._next_id
        self._next_id += 1
        self._pending[nid] = note
        return note

    def confirm_visit(self, note_id: int) -> VisitNote:
        """Human-approved: add a new evidence item, or update an existing one."""
        note = self._pending.get(note_id)
        if note is None:
            raise ValueError(f"Unknown pending note {note_id}")
        hist = self._histories[note.patient_id]

        if note.target_evidence_id:                       # UPDATE path
            target = next((i for i in hist.items
                           if i.evidence_id == note.target_evidence_id), None)
            if target is None:
                raise ValueError(f"No evidence {note.target_evidence_id} to update")
            target.text = note.summary
            audit_eid, action = note.target_evidence_id, "update"
        else:                                             # ADD path
            audit_eid = f"E{len(hist.items) + 1}"
            hist.items.append(
                EvidenceItem(evidence_id=audit_eid, kind=note.kind,
                             text=note.summary, source="staff-entered")
            )
            action = "add"

        note.status = "confirmed"
        self.store.add_record_audit(
            patient_id=note.patient_id, action=action, evidence_id=audit_eid,
            kind=str(note.kind), content=note.summary, author=note.author,
        )
        return note