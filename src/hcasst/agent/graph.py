"""LangGraph orchestration of the healthcare assistant.

Flow: plan -> identify -> route -> {summarize|disease|book} -> route ... ->
      guardrail -> respond -> memory -> END
Services are bound into the HealthAssistant facade. Every node writes a
PHI-masked trace for the dashboard (Part 2 observability).
"""

from __future__ import annotations

import uuid
from typing import Any

from langgraph.graph import END, START, StateGraph

from config.settings import Settings, get_settings
from hcasst.agent import planner
from hcasst.agent.guardrails import grounding_check
from hcasst.agent.state import AgentState
from hcasst.agent.summarize import summarize_history, synthesize_disease_info
from hcasst.db.store import Store
from hcasst.llm.provider import get_llm
from hcasst.memory.store import MemoryManager
from hcasst.obs.logging import get_logger, mask_obj
from hcasst.tools.disease_search import DiseaseSearch
from hcasst.tools.records import RecordsManager
from hcasst.tools.scheduling import Scheduler

log = get_logger("graph")

_TOOL_TO_NODE = {"summarize_history": "summarize",
                 "search_disease_info": "disease",
                 "book_appointment": "book"}


class HealthAssistant:
    def __init__(self, settings: Settings | None = None, store: Store | None = None) -> None:
        self.settings = settings or get_settings()
        self.llm = get_llm(self.settings)
        self.store = store or Store()
        self.records = RecordsManager(self.settings, store=self.store)
        self.scheduler = Scheduler(store=self.store)
        self.search = DiseaseSearch(self.settings)
        self.memory = MemoryManager(self.settings, store=self.store)
        self.graph = self._build()

    def _trace(self, state: AgentState, step: str, name: str, status: str, payload: Any) -> None:
        try:
            self.store.add_trace(state.get("session_id", "?"), step, name, status, mask_obj(payload))
        except Exception as exc:  # noqa: BLE001
            log.warning("trace write failed: %s", exc)

    def _plan(self, state: AgentState) -> AgentState:
        plan = planner.make_plan(state["query"], state.get("patient_hint", ""), llm=self.llm)
        self._trace(state, "plan", "planner", "ok", {"steps": [s["tool"] for s in plan]})
        return {"plan": plan, "intent": state["query"], "executed": [],
                "errors": [], "needs_approval": False}

    def _identify(self, state: AgentState) -> AgentState:
        hint = state.get("patient_hint", "").strip() or "seed-001"
        history = self.records.get_patient_history(hint)
        self.memory.index_patient(history)
        self._trace(state, "tool", "get_patient_history", "ok",
                    {"patient": history.patient.label, "evidence_items": len(history.items)})
        return {"patient": history.patient, "history": history,
                "executed": list(state.get("executed", [])) + ["get_patient_history"]}
    
    def _summarize(self, state: AgentState) -> AgentState:
        summary, citations = summarize_history(state["history"], state["query"], self.memory, llm=self.llm)
        self._trace(state, "tool", "summarize_history", "ok", {"citations": citations})
        return {"summary": summary, "summary_citations": citations,
                "executed": list(state.get("executed", [])) + ["summarize_history"]}

    def _disease(self, state: AgentState) -> AgentState:
        topic = planner.topic_of(state["query"], state.get("history"))
        results = self.search.search(topic)
        answer, used = synthesize_disease_info(topic, results, llm=self.llm)
        self._trace(state, "tool", "search_disease_info", "ok", {"topic": topic, "n_sources": len(used)})
        return {"disease_answer": answer, "disease_sources": used,
                "executed": list(state.get("executed", [])) + ["search_disease_info"]}

    def _book(self, state: AgentState) -> AgentState:
        specialty = planner.specialty_of(state["query"])
        urgency = planner.urgency_of(state["query"])
        try:
            proposal = self.scheduler.propose_booking(state["patient"], specialty,
                                                      urgency=urgency, reason=state["query"][:120])
            payload = {"specialty": specialty, "provider": proposal.provider,
                       "proposal_id": proposal.proposal_id}
        except Exception as exc:  # noqa: BLE001
            self._trace(state, "tool", "book_appointment", "error", {"error": str(exc)})
            return {"errors": list(state.get("errors", [])) + [f"booking failed: {exc}"],
                    "executed": list(state.get("executed", [])) + ["book_appointment"]}
        # HITL: proposal created but NOT confirmed — approval happens in the UI.
        self._trace(state, "guardrail", "human_approval_gate", "blocked", payload)
        return {"booking_proposal": proposal, "needs_approval": True,
                "executed": list(state.get("executed", [])) + ["book_appointment"]}

    def _guardrail(self, state: AgentState) -> AgentState:
        summary = state.get("summary", "")
        if not summary:
            return {"grounding": {"grounded": True, "uncited_claims": [], "rationale": "no summary"}}
        verdict = grounding_check(summary, state["history"].evidence_block(), llm=self.llm)
        self._trace(state, "guardrail", "grounding_check",
                    "ok" if verdict.get("grounded") else "blocked", verdict)
        return {"grounding": verdict}

    def _respond(self, state: AgentState) -> AgentState:
        response = _assemble_response(state)
        self._trace(state, "respond", "assemble", "ok", {"chars": len(response)})
        return {"response": response}

    def _memory(self, state: AgentState) -> AgentState:
        if state.get("summary") and state.get("patient"):
            self.memory.remember(state["patient"].id, state["summary"], kind="summary")
        return {}
    @staticmethod
    def _choose_next(state: AgentState) -> str:
        executed = set(state.get("executed", []))
        for step in state.get("plan", []):
            tool = step["tool"]
            if tool in _TOOL_TO_NODE and tool not in executed:
                return _TOOL_TO_NODE[tool]
        return "done"

    def _build(self):
        g = StateGraph(AgentState)
        g.add_node("planner", self._plan)
        g.add_node("identify", self._identify)
        g.add_node("route", lambda s: {})            # passthrough; routing is in the edge fn
        g.add_node("summarize", self._summarize)
        g.add_node("disease", self._disease)
        g.add_node("book", self._book)
        g.add_node("guardrail", self._guardrail)
        g.add_node("respond", self._respond)
        g.add_node("memory", self._memory)

        g.add_edge(START, "planner")
        g.add_edge("planner", "identify")
        g.add_edge("identify", "route")
        g.add_conditional_edges("route", self._choose_next,
            {"summarize": "summarize", "disease": "disease", "book": "book", "done": "guardrail"})
        for node in ("summarize", "disease", "book"):
            g.add_edge(node, "route")
        g.add_edge("guardrail", "respond")
        g.add_edge("respond", "memory")
        g.add_edge("memory", END)
        return g.compile()

    def run(self, query: str, patient_hint: str = "", session_id: str | None = None) -> AgentState:
        session_id = session_id or uuid.uuid4().hex[:12]
        initial: AgentState = {"session_id": session_id, "query": query, "patient_hint": patient_hint}
        log.info("Running session %s: %s", session_id, query)
        return self.graph.invoke(initial)


def _assemble_response(state: AgentState) -> str:
    patient = state.get("patient")
    parts: list[str] = []
    if patient is not None:
        parts.append(f"**Patient:** {patient.label}")
    if state.get("summary"):
        parts.append("### Medical History Summary\n" + state["summary"])
    proposal = state.get("booking_proposal")
    if proposal is not None:
        lines = ["### Proposed Appointment — awaiting your approval",
                 f"- **Specialty:** {proposal.specialty}",
                 f"- **Provider:** {proposal.provider}",
                 f"- **When:** {proposal.start}",
                 "\n> No booking is made until you approve it (human-in-the-loop)."]
        parts.append("\n".join(lines))
    if state.get("disease_answer"):
        parts.append("### Latest Information (cited)\n" + state["disease_answer"])
    g = state.get("grounding") or {}
    if g and not g.get("grounded", True):
        parts.append("> Grounding check flagged unverified statements; clinician review advised.")
    if state.get("errors"):
        parts.append("> Notes: " + "; ".join(state["errors"]))
    return "\n\n".join(parts) if parts else "No response generated."


def serialize_state(state: AgentState) -> dict:
    patient = state.get("patient")
    proposal = state.get("booking_proposal")
    return {
        "session_id": state.get("session_id"),
        "query": state.get("query"),
        "patient": {"id": patient.id, "label": patient.label} if patient else None,
        "plan": state.get("plan", []),
        "summary": state.get("summary", ""),
        "summary_citations": state.get("summary_citations", []),
        "disease_answer": state.get("disease_answer", ""),
        "disease_sources": state.get("disease_sources", []),
        "booking": {"proposal_id": proposal.proposal_id, "specialty": proposal.specialty,
                    "provider": proposal.provider, "start": proposal.start,
                    "needs_approval": state.get("needs_approval", False)} if proposal else None,
        "grounding": state.get("grounding", {}),
        "response": state.get("response", ""),
    }

    

