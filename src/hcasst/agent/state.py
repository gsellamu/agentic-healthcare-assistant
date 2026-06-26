"""LangGraph state schema — one TypedDict threaded through every node.

Nodes return partial updates that LangGraph merges into the running state.
Non-JSON objects (Patient, PatientHistory, BookingProposal) are held as-is
during a run; serialize_state converts them to dicts for the UI.
"""

from __future__ import annotations

from typing import Any, TypedDict


class PlanStep(TypedDict):
    goal: str
    tool: str


class AgentState(TypedDict, total=False):
    session_id: str
    query: str
    patient_hint: str

    patient: Any
    history: Any

    plan: list[PlanStep]
    intent: str
    executed: list[str]

    summary: str
    summary_citations: list[str]
    disease_answer: str
    disease_sources: list[dict]
    booking_proposal: Any
    needs_approval: bool

    grounding: dict
    errors: list[str]

    response: str

    
    