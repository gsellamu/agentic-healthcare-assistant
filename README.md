# Agentic Healthcare Assistant (HCAsst)

A virtual medical assistant that automates clinical-support tasks — booking
appointments, managing patient records, summarizing history, and searching
disease information — built as a **LangGraph agent** with **RAG**, **long-term
memory**, a **zero-hallucination guardrail**, **human-in-the-loop** writes, and
an **LLMOps evaluation** harness. Runs fully **offline** by default; plug in an
Anthropic key for real Claude.

> Capstone for the Applied Generative AI Specialization.

## Quick start

```powershell
cd capstone
python -m venv venv311
venv311\Scripts\activate
pip install -r requirements.txt
copy .env.example .env            # leave the key blank to run offline
streamlit run app/streamlit_app.py
```

Open http://localhost:8501. (First run downloads a ~80 MB embedding model.)

## What it does (the four services)

1. **Book appointments** — slot discovery + scheduling from patient intent;
   proposed for human approval, never auto-booked.
2. **Manage records** — add/update structured **and** unstructured history,
   propose -> confirm, fully audited.
3. **Retrieve histories** — RAG-backed, cited summaries of diagnoses, meds,
   and alerts.
4. **Search disease info** — MedlinePlus (NLM) + PubMed (NCBI), with an offline
   knowledge-base fallback.

## Architecture in one line

`plan -> identify -> route <-> {summarize | disease | book} -> guardrail ->
respond -> memory` — a LangGraph state machine where one router loops until the
plan is exhausted, every node is traced (PHI-masked), and no clinical claim
leaves without a citation.

See `docs/01_ARD.md` for the design decisions and `docs/02_TECHNICAL_SPEC.md`
for the build.

## The sample scenario

> "My 70-year-old father has chronic kidney disease. I want to book a
> nephrologist for him. Also, can you summarize the latest treatment methods?"

The agent decomposes this into get_patient_history -> book_appointment ->
summarize_history -> search_disease_info, proposes a nephrology booking
(awaiting approval), and returns a cited summary plus cited treatment info.

## Design pillars

- **Zero-hallucination** — citation check + LLM-judge grounding; regenerate up
  to 3x, then caveat rather than invent.
- **Human-in-the-loop** — bookings and record edits are proposed, then confirmed
  by a human.
- **PHI-safe** — emails/phones/SSN/DOB masked before any log or trace is stored
  (HIPAA-*aligned*).
- **Offline-first** — deterministic MockLLM + hashing-embedder fallback so the
  whole system runs and tests reproducibly with no key and no network.

## Layout

```
config/        settings (offline switch)
src/hcasst/    models, llm, tools, rag, memory, agent, eval, db, obs
app/           Streamlit dashboard (6 views)
data/seed/     seed patients
docs/          ARD, Technical Spec, Implementation Guide, User Guide, Playbook
tests/         tests
```

## Evaluation

```powershell
python -c "import sys; sys.path.insert(0,'src'); sys.path.insert(0,'config'); from hcasst.eval.runner import run_evaluation; print(run_evaluation()['metrics'])"
```

Scores tool-selection F1, booking success, citation coverage, QA correctness,
and grounding over golden cases; results persist to the `eval_runs` table and
render in the dashboard's Evaluation view.

## Documentation

In-app (Documentation view) or in `docs/`:

| Doc | Role |
|-----|------|
| `01_ARD.md` | Architecture decisions — the strategy |
| `02_TECHNICAL_SPEC.md` | How it's built — the construction |
| `03_IMPLEMENTATION_GUIDE.md` | Install & connect — the setup |
| `04_USER_GUIDE.md` | Click-through — the daily use |
| `05_PLAYBOOK.md` | Scenarios & fixes — the operations |

## Security

`.env` may hold a real API key and is git-ignored — never commit it. Ship
`.env.example` (no secret). If a key leaks, revoke it at console.anthropic.com
and mint a new one.
