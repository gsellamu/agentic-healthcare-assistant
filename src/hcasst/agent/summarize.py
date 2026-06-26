"""Cited summarization and disease-info synthesis (RAG-backed LLM steps).

Both retrieve evidence, generate with the LLM, and run the regenerate-until-
grounded loop — so output is always cited or explicitly caveated.
"""

from __future__ import annotations

from hcasst.agent.guardrails import generate_grounded
from hcasst.llm import prompts
from hcasst.llm.provider import LLM, get_llm
from hcasst.memory.store import MemoryManager
from hcasst.models import PatientHistory, SearchResult
from hcasst.rag.ingest import search_results_to_documents
from hcasst.rag.vectorstore import VectorStore


def summarize_history(history: PatientHistory, focus: str, memory: MemoryManager,
                      llm: LLM | None = None, k: int = 8) -> tuple[str, list[str]]:
    llm = llm or get_llm()
    memory.index_patient(history)
    recalled = memory.recall(history.patient.id, focus or "overall medical history", k=k)
    evidence = recalled.as_evidence() or history.evidence_block()
    citations = [r.document.citation for r in recalled.items] or \
                [f"[{i.evidence_id}]" for i in history.items]

    def _gen() -> str:
        return llm.complete(
            prompts.SUMMARY_SYSTEM,
            prompts.SUMMARY_USER.format(patient_label=history.patient.label,
                                        evidence=evidence, focus=focus or "general"),
        )

    summary, verdict, loops = generate_grounded(_gen, evidence, llm=llm)
    return summary, citations


def synthesize_disease_info(topic: str, results: list[SearchResult],
                            llm: LLM | None = None, k: int = 6) -> tuple[str, list[dict]]:
    llm = llm or get_llm()
    vs = VectorStore()
    vs.add(search_results_to_documents(results))
    retrieved = vs.query(topic, k=k) if len(vs) else []
    sources_block = "\n".join(f"{r.document.citation} {r.document.text}" for r in retrieved) \
                    or "\n".join(r.cite() for r in results)

    def _gen() -> str:
        return llm.complete(prompts.DISEASE_SYSTEM,
                            prompts.DISEASE_USER.format(topic=topic, sources=sources_block))

    answer, verdict, loops = generate_grounded(_gen, sources_block, llm=llm)
    used = [{"citation": r.document.citation, "source": r.document.source} for r in retrieved] \
           or [{"citation": r.citation, "source": r.source, "url": r.url} for r in results]
    return answer, used

