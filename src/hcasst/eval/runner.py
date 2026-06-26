"""Eval harness: run golden cases, score, persist to eval_runs.

    python -m hcasst.eval.runner
"""

from __future__ import annotations

import sys
import uuid
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "config"))

from config.settings import Settings, get_settings
from hcasst.agent.graph import HealthAssistant, serialize_state
from hcasst.db.store import Store
from hcasst.eval import evaluators as ev
from hcasst.eval.datasets import GOLDEN_CASES, EvalCase
from hcasst.obs.logging import get_logger

log = get_logger("eval")


def evaluate_case(case: EvalCase, assistant: HealthAssistant) -> list[tuple[str, str, float, dict]]:
    state = assistant.run(case.query, patient_hint=case.patient_hint)
    result = serialize_state(state)
    actual = list(state.get("executed", []))
    rows: list[tuple[str, str, float, dict]] = []

    f1, d = ev.tool_f1(case.expected_tools, actual)
    rows.append(("planning", "tool_f1", f1, d))

    booking = result.get("booking")
    val, d = ev.booking_success(case.expects_booking, case.booking_specialty,
                                booking is not None, (booking or {}).get("specialty", ""))
    rows.append(("booking", "success", val, d))

    llm = assistant.llm
    if result.get("summary"):
        qa, d = ev.qa_correctness(case.query, case.reference_summary, result["summary"], llm)
        rows.append(("summary", "qa_correctness", qa, d))
        cov, d = ev.citation_coverage(result["summary"])
        rows.append(("summary", "citation_coverage", cov, d))
    if result.get("disease_answer"):
        qa, d = ev.qa_correctness(case.query, case.reference_disease, result["disease_answer"], llm)
        rows.append(("search", "qa_correctness", qa, d))
        cov, d = ev.citation_coverage(result["disease_answer"])
        rows.append(("search", "citation_coverage", cov, d))

    grounded = 1.0 if result.get("grounding", {}).get("grounded", True) else 0.0
    rows.append(("grounding", "grounded", grounded, result.get("grounding", {})))
    return rows


def run_evaluation(settings: Settings | None = None, store: Store | None = None,
                   run_id: str | None = None) -> dict:
    settings = settings or get_settings()
    store = store or Store()
    assistant = HealthAssistant(settings, store=store)
    run_id = run_id or uuid.uuid4().hex[:12]
    log.info("Eval run %s (%d cases, llm=%s)", run_id, len(GOLDEN_CASES), assistant.llm.name)

    agg: dict[tuple[str, str], list[float]] = defaultdict(list)
    for case in GOLDEN_CASES:
        for module, metric, value, detail in evaluate_case(case, assistant):
            store.add_eval(run_id, f"{module}:{case.id}", metric, value, detail)
            agg[(module, metric)].append(value)

    summary = {f"{m}.{k}": round(sum(v) / len(v), 3) for (m, k), v in sorted(agg.items())}
    summary["OVERALL"] = round(sum(summary.values()) / len(summary), 3) if summary else 0.0
    for key, val in summary.items():
        store.add_eval(run_id, "summary", key, val, None)
    return {"run_id": run_id, "llm": assistant.llm.name, "metrics": summary}


if __name__ == "__main__":
    r = run_evaluation()
    print(f"\nEval {r['run_id']} (llm={r['llm']})")
    for k, v in r["metrics"].items():
        print(f"  {k:<28} {v:>6.3f} {'#' * int(round(v * 20))}")

        