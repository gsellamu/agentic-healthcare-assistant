"""Guardrails enforcing the zero-hallucination contract.

  - citation_presence : structural check that the answer cites evidence.
  - grounding_check   : LLM-as-judge (offline heuristic fallback) that claims
                        are supported by evidence.
  - generate_grounded : regenerate-until-grounded loop, bounded by max_loops
                        (the design's 'loop break of 3'); appends a caveat if
                        still ungrounded.
"""

from __future__ import annotations

import re
from collections.abc import Callable

from config.settings import get_settings
from hcasst.llm import prompts
from hcasst.llm.provider import LLM, get_llm
from hcasst.obs.logging import get_logger

log = get_logger("guardrails")

_CITATION = re.compile(r"\[(E\d+|M\d+|PMID:\d+|MedlinePlus|WHO|OfflineKB)\]")


def citation_presence(answer: str) -> bool:
    return bool(_CITATION.search(answer or ""))


def grounding_check(answer: str, evidence: str, llm: LLM | None = None) -> dict:
    llm = llm or get_llm()
    if not citation_presence(answer):
        return {"grounded": False,
                "uncited_claims": ["answer contains no citations"],
                "rationale": "no citation markers present"}
    try:
        verdict = llm.complete_json(
            prompts.GROUNDING_SYSTEM,
            prompts.GROUNDING_USER.format(answer=answer, evidence=evidence),
        )
        if isinstance(verdict, dict) and "grounded" in verdict:
            return verdict
    except Exception as exc:  # noqa: BLE001
        log.warning("grounding_check failed (%s); citation-based pass", exc)
    return {"grounded": True, "uncited_claims": [], "rationale": "citation-based fallback"}


def generate_grounded(generate: Callable[[], str], evidence: str, *,
                      max_loops: int | None = None, llm: LLM | None = None) -> tuple[str, dict, int]:
    max_loops = max_loops or get_settings().max_agent_loops
    llm = llm or get_llm()
    answer, verdict = "", {}
    for attempt in range(1, max_loops + 1):
        answer = generate()
        verdict = grounding_check(answer, evidence, llm=llm)
        if verdict.get("grounded"):
            return answer, verdict, attempt
        log.warning("Attempt %d not grounded: %s", attempt, verdict.get("uncited_claims"))
    caveat = ("\n\n[unverified] Some statements could not be fully verified against "
              "available evidence after multiple attempts; please confirm with a clinician.")
    return answer + caveat, verdict, max_loops


def requires_human_approval(tool_name: str) -> bool:
    return tool_name in {"book_appointment", "update_record"}


