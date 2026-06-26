"""LLMOps evaluators — all return (float in [0,1], detail dict)."""

from __future__ import annotations

import re

from hcasst.agent.guardrails import _CITATION
from hcasst.llm import prompts
from hcasst.llm.provider import LLM, get_llm

_TOKEN = re.compile(r"[a-z0-9]+")
_BULLET = re.compile(r"^([-*]|\d+\.)\s+")
_STOP = {"the", "a", "an", "and", "or", "of", "to", "in", "is", "with", "for", "on", "at"}


def _tokens(text: str) -> set[str]:
    return {t for t in _TOKEN.findall(text.lower()) if t not in _STOP and len(t) > 2}


def qa_correctness(question: str, reference: str, prediction: str,
                   llm: LLM | None = None) -> tuple[float, dict]:
    llm = llm or get_llm()
    if not prediction.strip():
        return 0.0, {"grade": "INCORRECT", "reason": "empty prediction"}
    if llm.name == "mock" or not reference:
        ref, pred = _tokens(reference), _tokens(prediction)
        if not ref:
            return 1.0, {"grade": "CORRECT", "reason": "no reference terms"}
        overlap = len(ref & pred) / len(ref)
        return round(overlap, 3), {"grade": "CORRECT" if overlap >= 0.34 else "PARTIAL",
                                   "reason": f"recall={overlap:.2f}", "method": "token-overlap"}
    verdict = llm.complete_json(prompts.QAEVAL_SYSTEM,
        prompts.QAEVAL_USER.format(question=question, reference=reference, prediction=prediction))
    score = float(verdict.get("score", 1.0 if verdict.get("grade") == "CORRECT" else 0.0))
    return score, {"grade": verdict.get("grade"), "reason": verdict.get("rationale"), "method": "llm-judge"}


def citation_coverage(answer: str) -> tuple[float, dict]:
    answer = answer or ""
    claims = [ln.strip() for ln in answer.splitlines() if _BULLET.match(ln.strip())]
    if not claims:
        claims = [s.strip() for s in re.split(r"(?<=[.])\s+", answer)
                  if len(s.strip()) > 30 and not s.strip().startswith(("#", ">"))]
    if not claims:
        return 0.0, {"claims": 0}
    cited = sum(1 for c in claims if _CITATION.search(c))
    return round(cited / len(claims), 3), {"claims": len(claims), "cited": cited}


def tool_f1(expected: list[str], actual: list[str]) -> tuple[float, dict]:
    exp, act = set(expected), set(actual)
    if not exp and not act:
        return 1.0, {"precision": 1.0, "recall": 1.0}
    tp = len(exp & act)
    precision = tp / len(act) if act else 0.0
    recall = tp / len(exp) if exp else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return round(f1, 3), {"precision": round(precision, 3), "recall": round(recall, 3),
                          "expected": sorted(exp), "actual": sorted(act)}


def booking_success(expects_booking: bool, specialty: str, proposed: bool,
                    proposed_specialty: str) -> tuple[float, dict]:
    if not expects_booking:
        return (1.0 if not proposed else 0.0), {"expected": False, "proposed": proposed}
    if not proposed:
        return 0.0, {"expected": True, "proposed": False}
    match = specialty.lower() in (proposed_specialty or "").lower()
    return (1.0 if match else 0.5), {"expected_specialty": specialty,
                                     "proposed_specialty": proposed_specialty, "specialty_match": match}

                                     