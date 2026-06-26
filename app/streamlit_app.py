"""Agentic Healthcare Assistant — Streamlit dashboard.
Run: streamlit run app/streamlit_app.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import json
import os

import pandas as pd
import plotly.express as px
import streamlit as st

from config.settings import get_settings
from hcasst.agent.graph import HealthAssistant, serialize_state
from hcasst.db.store import Store
from hcasst.llm.provider import reset_llm
from hcasst.tools.records import RecordsManager

st.set_page_config(page_title="Agentic Healthcare Assistant", page_icon="H", layout="wide")


@st.cache_resource
def _store() -> Store:
    return Store()


@st.cache_resource
def _assistant() -> HealthAssistant:
    return HealthAssistant(store=_store())


@st.cache_resource
def _records() -> RecordsManager:
    return RecordsManager(store=_store())


# ── sidebar: backend toggle (offline-first + UI key, per design.md) ──────
st.sidebar.title("Settings")
s = get_settings()
st.sidebar.caption(f"LLM backend: **{'Claude' if s.llm_available else 'Offline Mock'}**")
key_in = st.sidebar.text_input("ANTHROPIC_API_KEY (optional)", type="password",
                               help="Paste a key to use real Claude; blank = offline mock.")
if st.sidebar.button("Apply key"):
    os.environ["ANTHROPIC_API_KEY"] = key_in
    get_settings.cache_clear()
    reset_llm()
    st.rerun()
st.sidebar.caption(f"Appointments on record: {len(_store().appointments())}")

view = st.sidebar.radio("View", ["Assistant", "Patient", "Doctor", "Evaluation", "Traces", "Documentation"])

# ── Assistant (scenario tester) ──────────────────────────────────────────
if view == "Assistant":
    st.title("Agentic Healthcare Assistant")
    patients = _records().list_patients()
    pmap = {p.label: p.id for p in patients}
    psel = st.selectbox("Patient", list(pmap.keys()))
    examples = {
        "CKD + nephrologist (golden)": "My 70-year-old father has chronic kidney disease. I want to book a nephrologist for him. Also, can you summarize the latest treatment methods?",
        "Summarize history": "Summarize this patient's medical history.",
        "Disease info": "What are the latest treatment methods for chronic kidney disease?",
    }
    ex = st.selectbox("Example", list(examples.keys()))
    query = st.text_area("Patient request", value=examples[ex], height=100)

    if st.button("Run assistant", type="primary") and query.strip():
        with st.spinner("Planning and executing..."):
            st.session_state["state"] = _assistant().run(query, patient_hint=pmap[psel])

    state = st.session_state.get("state")
    if state:
        st.subheader("Plan")
        plan = state.get("plan", [])
        cols = st.columns(len(plan) or 1)
        for col, step in zip(cols, plan):
            done = step["tool"] in state.get("executed", [])
            col.metric(step["tool"], "done" if done else "-", help=step["goal"])

        st.subheader("Response")
        st.markdown(state.get("response", "_none_"))

        prop = state.get("booking_proposal")
        if prop is not None and state.get("needs_approval"):
            st.warning("Booking proposed — awaiting approval (no write yet).")
            a, b, _ = st.columns([1, 1, 4])
            if a.button("Approve & book"):
                r = _assistant().scheduler.confirm_booking(prop.proposal_id)
                st.success(f"Booked (status={r.status}).")
            if b.button("Reject"):
                _assistant().scheduler.reject_booking(prop.proposal_id)
                st.info("Rejected. No appointment created.")

        g = state.get("grounding") or {}
        with st.expander("Guardrail / grounding verdict"):
            if g.get("grounded", True):
                st.success("Grounded.")
            else:
                st.error(f"Ungrounded: {g.get('uncited_claims')}")
            st.json(g)
        with st.expander("Evidence & sources"):
            st.write("Summary citations:", ", ".join(state.get("summary_citations", [])))
            st.json(state.get("disease_sources", []))
        st.caption(f"Session `{state.get('session_id')}` — see Traces.")

# ── Patient view ─────────────────────────────────────────────────────────
elif view == "Patient":
    st.title("Patient View")
    patients = _records().list_patients()
    pmap = {p.label: p.id for p in patients}
    psel = st.selectbox("Patient", list(pmap.keys()))
    pid = pmap[psel]
    h = _records().get_patient_history(pid)
    st.subheader("Medical history")
    st.dataframe(pd.DataFrame([{"id": i.evidence_id, "kind": str(i.kind),
                                "text": i.text, "date": i.date} for i in h.items]),
                 use_container_width=True)

    st.subheader("Manage record (add / update)  \u2014  human-in-the-loop")
    from hcasst.models import EvidenceKind
    kinds = [k.value for k in EvidenceKind]
    c1, c2 = st.columns([1, 2])
    kind = c1.selectbox("Kind (note = unstructured; others = structured)", kinds, index=kinds.index("note"))
    target = c1.text_input("Update evidence id (blank = add new)", "")
    text = c2.text_area("Record text", "Follow-up: patient stable, continue current regimen.", height=80)
    if c2.button("Propose record change"):
        mgr = _records()
        note = mgr.propose_visit(pid, text, kind=EvidenceKind(kind),
                                 target_evidence_id=target.strip())
        # propose_visit assigns mgr._next_id-1 as this note's pending id
        st.session_state["pending_nid"] = mgr._next_id - 1
        st.session_state["pending_kind"] = str(note.kind)
        st.rerun()

    nid = st.session_state.get("pending_nid")
    if nid is not None:
        action = "update" if target.strip() else "add"
        st.warning(f"Proposed ({st.session_state.get('pending_kind')}, {action}) \u2014 awaiting confirmation. No write yet.")
        cc1, cc2, _ = st.columns([1, 1, 4])
        if cc1.button("Confirm record change"):
            _records().confirm_visit(nid)
            st.session_state["pending_nid"] = None
            st.success("Record change committed and audited. See Doctor view audit.")
            st.rerun()
        if cc2.button("Cancel"):
            st.session_state["pending_nid"] = None
            st.info("Cancelled. No change.")
            st.rerun()

    st.subheader("Appointments")
    st.dataframe(pd.DataFrame(_store().appointments(pid)), use_container_width=True)

# ── Doctor view ──────────────────────────────────────────────────────────
elif view == "Doctor":
    st.title("Doctor View — Appointment Tracking")
    appts = _store().appointments()
    if appts:
        df = pd.DataFrame(appts)
        st.dataframe(df, use_container_width=True)
        st.bar_chart(df["status"].value_counts())
    else:
        st.info("No appointments yet. Run the assistant and approve a booking.")
    st.subheader("Record-change audit")
    st.dataframe(pd.DataFrame(_store().record_audit()), use_container_width=True)

# ── Evaluation ───────────────────────────────────────────────────────────
elif view == "Evaluation":
    st.title("LLMOps Evaluation")
    if st.button("Run evaluation"):
        from hcasst.eval.runner import run_evaluation
        with st.spinner("Evaluating golden cases..."):
            run_evaluation(store=_store())
        st.rerun()
    rid = _store().latest_run_id()
    if rid:
        rows = [r for r in _store().eval_runs(rid) if r["module"] == "summary"]
        df = pd.DataFrame([{"metric": r["metric"], "value": r["value"]} for r in rows
                           if r["metric"] not in ("OVERALL",)])
        overall = next((r["value"] for r in rows if r["metric"] == "OVERALL"), None)
        if overall is not None:
            st.metric("OVERALL", f"{overall:.3f}")
        if not df.empty:
            st.plotly_chart(px.bar(df, x="metric", y="value", range_y=[0, 1]),
                            use_container_width=True)
            st.dataframe(df, use_container_width=True)
    else:
        st.info("No eval runs yet. Click Run evaluation.")

# ── Traces ───────────────────────────────────────────────────────────────
elif view == "Traces":
    st.title("Agent Traces & Tool Logs")
    sid = st.text_input("Session id (blank = latest)")
    traces = _store().traces(sid.strip() or None, limit=200)
    if traces:
        df = pd.DataFrame([{"step": t["step"], "name": t["name"], "status": t["status"],
                            "payload": t["payload"]} for t in traces])
        st.dataframe(df, use_container_width=True)
        st.subheader("Tool success/failure")
        st.bar_chart(df["status"].value_counts())
    else:
        st.info("No traces. Run the assistant first.")

elif view == "Documentation":
    st.title("Documentation")
    DOCS = {
        "ARD \u2014 Architecture (The Strategy)": "01_ARD.md",
        "Technical Spec (The Construction)": "02_TECHNICAL_SPEC.md",
        "Implementation Guide (The Setup)": "03_IMPLEMENTATION_GUIDE.md",
        "User Guide (The Daily Use)": "04_USER_GUIDE.md",
        "Playbook (The Operations)": "05_PLAYBOOK.md",
    }
    choice = st.selectbox("Select a document", list(DOCS.keys()))
    doc_path = ROOT / "docs" / DOCS[choice]
    if doc_path.exists():
        st.markdown(doc_path.read_text(encoding="utf-8"))
    else:
        st.warning(f"Missing: docs/{DOCS[choice]} \u2014 create it at {doc_path}")


        