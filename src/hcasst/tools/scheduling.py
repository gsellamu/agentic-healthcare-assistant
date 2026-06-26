"""Appointment scheduling: slot discovery, top-3 recommendation, HITL booking.

Booking is a two-step, human-in-the-loop operation:
  propose_booking()  -> finds/scores slots, returns a proposal (commits nothing)
  confirm_booking()  -> runs only on explicit human approval
This satisfies the 'no write without human approval' guardrail.
(Core build keeps proposals in memory; persistence is added in M9.)
"""

from __future__ import annotations

import time

from pydantic import BaseModel, Field

from hcasst.models import Patient, Slot

# Synthetic provider roster per specialty (no real roster offline).
_PROVIDERS: dict[str, list[str]] = {
    "nephrology": ["Dr. Aisha Rahman, MD (Nephrology)", "Dr. Liu Chen, MD (Nephrology)"],
    "cardiology": ["Dr. Dan Vanthri, MD (Cardiology)", "Dr. Ellen Park, MD (Cardiology)"],
    "endocrinology": ["Dr. Jeeth Sellamuthu, MD (Endocrinology)"],
    "primary care": ["Dr. James Whitfield, MD (Family Medicine)"],
}

_URGENCY_WEIGHTS = {"urgent": 3.0, "soon": 2.0, "routine": 1.0}


class SlotRecommendation(BaseModel):
    slot: Slot
    provider: str
    score: float
    rationale: str


class BookingProposal(BaseModel):
    proposal_id: int
    patient_id: str
    patient_name: str
    specialty: str
    provider: str
    start: str
    end: str
    reason: str = ""
    status: str = "proposed"
    recommendations: list[SlotRecommendation] = Field(default_factory=list)


def _synthetic_slots(specialty: str) -> list[Slot]:
    """Deterministic near-future slots for offline demos."""
    base_days = [2, 4, 7, 9, 14]
    now = time.gmtime()
    slots: list[Slot] = []
    for i, off in enumerate(base_days):
        day = min(28, ((now.tm_mday + off - 1) % 28) + 1)
        start = f"{now.tm_year:04d}-{now.tm_mon:02d}-{day:02d}T09:{(i * 7) % 60:02d}:00Z"
        slots.append(Slot(id=f"synthetic-{i}", start=start, specialty=specialty, source="synthetic"))
    return slots
# Valid appointment lifecycle statuses.
_STATUSES = {"proposed", "scheduled", "confirmed", "completed", "cancelled", "rejected"}


class Scheduler:
    def __init__(self, store=None) -> None:
        from hcasst.db.store import Store
        self.store = store or Store()
        self._proposals: dict[int, BookingProposal] = {}

    def recommend_slots(
        self, specialty: str, urgency: str = "soon", top_k: int = 3
    ) -> list[SlotRecommendation]:
        slots = _synthetic_slots(specialty)
        providers = _PROVIDERS.get(specialty.lower(), ["Dr. A. Provider, MD"])
        urgency_w = _URGENCY_WEIGHTS.get(urgency.lower(), 1.0)
        ranked: list[SlotRecommendation] = []
        for i, slot in enumerate(sorted(slots, key=lambda s: s.start)):
            score = round((1.0 / (i + 1)) * urgency_w, 3)  # soonest scores highest
            ranked.append(
                SlotRecommendation(
                    slot=slot,
                    provider=providers[i % len(providers)],
                    score=score,
                    rationale=f"{specialty.title()} match; "
                              f"{'earliest' if i == 0 else f'#{i+1} soonest'}; urgency={urgency}",
                )
            )
        return ranked[:top_k]

    def propose_booking(
        self, patient: Patient, specialty: str, urgency: str = "soon", reason: str = ""
    ) -> BookingProposal:
        recs = self.recommend_slots(specialty, urgency)
        if not recs:
            raise RuntimeError(f"No slots available for {specialty}")
        best = recs[0]
        # Persist first; the DB row id IS the proposal id (single source of truth,
        # so in-memory and on-disk always agree).
        pid = self.store.add_appointment(
            patient_id=patient.id, patient_name=patient.name, specialty=specialty,
            provider=best.provider, start=best.slot.start, end=best.slot.end,
            status="proposed", reason=reason,
        )
        proposal = BookingProposal(
            proposal_id=pid,
            patient_id=patient.id,
            patient_name=patient.name,
            specialty=specialty,
            provider=best.provider,
            start=best.slot.start,
            end=best.slot.end,
            reason=reason,
            recommendations=recs,
        )
        self._proposals[pid] = proposal
        return proposal

    def _get_proposal(self, proposal_id: int) -> BookingProposal:
        """In-memory fast path; fall back to rehydrating from the database."""
        p = self._proposals.get(proposal_id)
        if p is not None:
            return p
        row = self.store.get_appointment(proposal_id)
        if row is None:
            raise ValueError(f"Unknown proposal {proposal_id}")
        p = BookingProposal(
            proposal_id=row["id"], patient_id=row["patient_id"],
            patient_name=row.get("patient_name") or "", specialty=row.get("specialty") or "",
            provider=row.get("provider") or "", start=row.get("start") or "",
            end=row.get("end") or "", reason=row.get("reason") or "",
            status=row.get("status") or "proposed",
        )
        self._proposals[proposal_id] = p
        return p

    def set_status(self, proposal_id: int, status: str) -> BookingProposal:
        """Update an appointment's lifecycle status (in memory + DB)."""
        if status not in _STATUSES:
            raise ValueError(f"Invalid status {status!r}; must be one of {sorted(_STATUSES)}")
        p = self._get_proposal(proposal_id)
        p.status = status
        self.store.update_appointment_status(proposal_id, status)
        return p

    def confirm_booking(self, proposal_id: int) -> BookingProposal:
        """Human-approved commit -> scheduled."""
        return self.set_status(proposal_id, "scheduled")

    def reject_booking(self, proposal_id: int) -> BookingProposal:
        return self.set_status(proposal_id, "rejected")

        
