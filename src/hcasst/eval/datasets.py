"""Golden evaluation cases."""

from __future__ import annotations

from pydantic import BaseModel, Field


class EvalCase(BaseModel):
    id: str
    query: str
    patient_hint: str
    expected_tools: list[str]
    expects_booking: bool = False
    booking_specialty: str = ""
    reference_summary: str = ""
    reference_disease: str = ""
    expected_keywords: list[str] = Field(default_factory=list)


GOLDEN_CASES: list[EvalCase] = [
    EvalCase(
        id="ckd-nephrology",
        query="My 70-year-old father has chronic kidney disease. I want to book a nephrologist for him. Also, can you summarize the latest treatment methods?",
        patient_hint="seed-001",
        expected_tools=["get_patient_history", "book_appointment", "summarize_history", "search_disease_info"],
        expects_booking=True, booking_specialty="nephrology",
        reference_summary="CKD stage 3b, type 2 diabetes, hypertension, lisinopril, empagliflozin, penicillin allergy.",
        reference_disease="ACE inhibitors/ARBs, glycemic control, SGLT2 inhibitors, avoid NSAIDs, monitor eGFR.",
        expected_keywords=["kidney", "egfr", "ace"],
    ),
    EvalCase(
        id="afib-cardiology",
        query="Book a cardiologist for Meera and summarize her heart history.",
        patient_hint="seed-002",
        expected_tools=["get_patient_history", "book_appointment", "summarize_history"],
        expects_booking=True, booking_specialty="cardiology",
        reference_summary="Atrial fibrillation, apixaban, CHA2DS2-VASc score 3.",
        expected_keywords=["atrial", "apixaban"],
    ),
    EvalCase(
        id="summary-only",
        query="Summarize my father's medical history.",
        patient_hint="seed-001",
        expected_tools=["get_patient_history", "summarize_history"],
        reference_summary="CKD stage 3b, diabetes, hypertension, lisinopril.",
        expected_keywords=["kidney", "diabetes"],
    ),
    EvalCase(
        id="disease-info-only",
        query="What are the latest treatment methods for chronic kidney disease?",
        patient_hint="seed-001",
        expected_tools=["get_patient_history", "search_disease_info"],
        reference_disease="ACE inhibitors/ARBs, SGLT2 inhibitors, avoid NSAIDs, monitor eGFR.",
        expected_keywords=["ace", "sglt2"],
    ),
]

