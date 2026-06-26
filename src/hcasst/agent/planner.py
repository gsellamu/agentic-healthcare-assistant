"""Planner: decompose a multi-step patient query into ordered tool sub-goals.

Asks the LLM (Claude or MockLLM) for a structured plan, validates it against the
known tool set, guarantees patient identification runs first, and de-duplicates
while preserving order. Falls back to keyword heuristics if the LLM plan is empty.
"""

from __future__ import annotations

import re

from hcasst.agent.state import PlanStep
from hcasst.llm import prompts
from hcasst.llm.provider import LLM, get_llm
from hcasst.obs.logging import get_logger

log = get_logger("planner")

VALID_TOOLS = {"get_patient_history", "book_appointment",
               "summarize_history", "search_disease_info"}

_SPECIALTIES = {"nephrolog": "nephrology", "kidney": "nephrology", "renal": "nephrology",
                "cardiolog": "cardiology", "heart": "cardiology",
                "endocrin": "endocrinology", "diabet": "endocrinology"}


def make_plan(query: str, patient_hint: str = "", llm: LLM | None = None) -> list[PlanStep]:
    llm = llm or get_llm()
    try:
        raw = llm.complete_json(
            prompts.PLANNER_SYSTEM,
            prompts.PLANNER_USER.format(query=query, patient_hint=patient_hint or "unspecified"),
        )
        steps = raw.get("steps", []) if isinstance(raw, dict) else []
    except Exception as exc:  # noqa: BLE001
        log.warning("LLM planning failed (%s); using heuristic plan", exc)
        steps = []

    plan: list[PlanStep] = []
    seen: set[str] = set()
    plan.append({"goal": "Identify patient and retrieve history", "tool": "get_patient_history"})
    seen.add("get_patient_history")

    for step in steps:
        tool = str(step.get("tool", "")).strip()
        if tool in VALID_TOOLS and tool not in seen:
            plan.append({"goal": str(step.get("goal", tool)), "tool": tool})
            seen.add(tool)

    if len(plan) == 1:                       # LLM gave nothing useful → heuristics
        plan.extend(_heuristic_steps(query, seen))
    return plan


def _heuristic_steps(query: str, seen: set[str]) -> list[PlanStep]:
    text = query.lower()
    extra: list[PlanStep] = []
    if any(k in text for k in ("book", "appointment", "schedule", "doctor", "specialist")) or specialty_of(query) != "primary care":
        if "book_appointment" not in seen:
            extra.append({"goal": "Find and propose appointment slots", "tool": "book_appointment"})
    if any(k in text for k in ("summar", "history", "record", "diagnos")):
        if "summarize_history" not in seen:
            extra.append({"goal": "Summarize history with citations", "tool": "summarize_history"})
    if any(k in text for k in ("latest", "treatment", "disease", "information", "method", "research")):
        if "search_disease_info" not in seen:
            extra.append({"goal": "Search trusted medical sources", "tool": "search_disease_info"})
    return extra


def specialty_of(query: str) -> str:
    text = query.lower()
    for key, specialty in _SPECIALTIES.items():
        if key in text:
            return specialty
    return "primary care"


def urgency_of(query: str) -> str:
    text = query.lower()
    if any(k in text for k in ("urgent", "asap", "emergency", "immediately", "today")):
        return "urgent"
    return "soon"


def topic_of(query: str, history=None) -> str:
    if history is not None and getattr(history, "conditions", None):
        return history.conditions[0].text
    cleaned = re.sub(r"\b(book|schedule|appointment|please|can you|i want to|for him|for her|my (father|mother|dad|mom))\b", "", query.lower())
    return cleaned.strip(" .,") or query

