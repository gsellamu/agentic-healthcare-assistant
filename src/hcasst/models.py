"""
 - Database data models used across tools and the agent.
 - Every clinical fact carries an 'evidence_id' and 'source' non-null mandatory so the summarizer and gaurdrais can enforce citation to enforce
    zero-hallucination bar.
 """

 # imports

import re # for regex and formated searrch and validations
from enum import Enum
from typing import Literal
from datetime import date
from pydantic import BaseModel, Field, field_validator # make use of pydantic schema and data clases


# define the class for patient

class Patient (BaseModel):
    id: str # patient id - keep it string for simplicity - not-null
    name: str # not null
    gender: str = "" # optional
    birth_date: str = "" # optional
    source: str = "FHIR" # default -> medical records via FHIR/HL7 Gateway

    @property
    def label(self) -> str:
        age = ""
        if self.birth_date[:4].isdigit(): # get year of birth
            age = f", ~{date.today().year - int(self.birth_date[:4])}y"
        return f"{self.name} ({self.gender}{age})".strip()


#curated and coverted/read patient FHIR record with evidence
class EvidenceKind(str, Enum):
    # supported FHIR/HL7 EHR event types
    CONDITION = "condition"
    MEDICATION = "medication"
    ENCOUNTER = "encounter"
    OBSERVATION = "observation"
    ALLERGY = "allergy"
    NOTE = "note"
    REPORT = "report"


class EvidenceItem(BaseModel):
    # one citable fact drawn from the patient record (FHIR/EHR record)
    evidence_id: str = Field (..., description="Unique evidence id matching the format 'E<number>'.")
    kind: EvidenceKind = Field(..., description = "FHIR/HL7 event type => {condition, medication, encounter, observation, allergy, note, report.")
    text: str = Field(..., description = "evidence description and details")
    date: str = Field(default="", description="clinical event timestamp")
    source: Literal["FHIR", "seed", "staff-entered", "MedlinePlus", "PubMed", "OfflineKB"] = Field(default="FHIR", description ="source of the record RAG/FHIR/HL7/API")

    @field_validator("evidence_id")
    @classmethod
    def _check_evidence_id(cls, v: str) -> str:
        if not re.fullmatch(r"E\d+", v):
            raise ValueError(f"evidence_id must match 'E<number>', got {v!r}")
        return v
    @classmethod
    def condition(cls, evidence_id: str, text: str, date: str = "") -> "EvidenceItem":
        """Factory for a condition fact — reads cleanly in seed data."""
        return cls(evidence_id=evidence_id, kind=EvidenceKind.CONDITION, text=text, date=date)

    def cite(self) -> str:
        tail = f" ({self.date})" if self.date else ""
        return f"[{self.evidence_id}] {self.text}{tail}"


class PatientHistory(BaseModel):
    patient: Patient
    items: list[EvidenceItem] = Field(default_factory=list)

    def by_kind(self, kind: str) -> list[EvidenceItem]:
        return [i for i in self.items if i.kind == kind]

    def evidence_block(self) -> str:
        """Render all facts as a citable block to inject into prompts."""
        return "\n".join(i.cite() for i in self.items) or "(no recorded history)"

    @property
    def conditions(self) -> list[EvidenceItem]:
        return self.by_kind("condition")
    
class Slot(BaseModel):
    #An available appointment slot.
    id: str
    start: str                    # ISO datetime
    end: str = ""
    specialty: str = ""
    provider: str = ""
    source: str = "FHIR"


class SearchResult(BaseModel):
    #One disease-information snippet from an external source.
    source: str                   # MedlinePlus | PubMed | WHO
    title: str
    snippet: str
    url: str = ""
    citation: str = ""            # e.g. "[MedlinePlus]" or "[PMID:12345]"

    def cite(self) -> str:
        return f"{self.citation} {self.title}: {self.snippet}".strip()
    


