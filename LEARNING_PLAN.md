# Capstone Learning Plan — Agentic Healthcare Assistant for Medical Task Automation

> **Goal:** build this capstone *myself*, typing every line, understanding it, and
> being able to explain/defend it to my instructor/TA. This plan is the shared
> checklist for me and my coding coach (desktop Claude).
>
> **Certification:** Simplilearn — Applied Generative AI Specialisation.
> **Spec PDF:** `../HCAsst-TaskAuto/1754386259_capstone_problem_statement_...pdf`
> **Reference implementation (gold standard to learn from):** `../HCAsst-TaskAuto/`
> **My build root:** this folder (`Purdue/capstone/`).

## How to use this plan

1. Work **one module at a time, top to bottom**. Don't skip ahead.
2. For each module, ask the coach to: (a) explain the concept + *why*, (b) show
   the code in small chunks, (c) walk through the key lines, (d) quiz me with the
   checkpoint questions, (e) tell me which file to type, (f) give me the "explain
   to instructor" summary.
3. Only mark a module ✅ when I can **run it** AND **explain it out loud**.
4. Build the **spec-required core (Modules 0–13)** first. The **Stretch** modules
   are my reference repo's extras — add them only after the core works and only
   if I can defend them.

## Academic-integrity guardrails

- I type/copy all code by hand after understanding it — no bulk paste of a
  finished project.
- For every module I write a 2–3 sentence "what this does and why" in my own
  words (collected in `NOTES.md`) — this becomes my viva cheat-sheet.
- If the coach simplifies away from the reference, note *what changed and why*.

---

## Spec → module map (so nothing is missed)

| Spec item (from PDF) | Covered by module |
| --- | --- |
| Part 1 · 1. Planner & goal decomposition | M6, M7 |
| Part 1 · 2. Tools (booking, EHR/records, disease search) | M3 |
| Part 1 · 2. Vector DB (FAISS) + long-term memory | M4, M5 |
| Part 1 · 3. Prompt engineering & task chaining | M2, M8 |
| Part 1 · 4. Sample flow (CKD → nephrologist + summary) | M10 |
| Part 2 · 6. Model evaluation (QAEval + per-module metrics) | M11 |
| Part 2 · 7. Streamlit dashboard (views, tracking, metrics) | M12, M13 |
| Part 2 · 8. Memory & logs interface (traces, planning) | M9, M13 |

---

# PART 0 — Foundations

## M0 · Environment & project scaffold
- **Build:** project folder layout, a dedicated `.venv`, `pyproject.toml`/
  `requirements.txt`, `config/settings.py` (config with safe offline defaults),
  `.env.example`.
- **Reference:** `pyproject.toml`, `config/settings.py`, `.env.example`.
- **Concepts to learn:** virtualenvs; why config is centralized; environment
  variables & secrets; the "offline-first" idea (app must run with no API key).
- **Checkpoint:** Why keep a dedicated venv? What does `settings.llm_available`
  decide? Where do API keys come from and what happens if none are set?
- **Run it:** `python -c "from config.settings import get_settings; print(get_settings())"`

## M1 · Shared data models
- **Build:** the dataclasses that carry data between tools/agent: `Patient`,
  `EvidenceItem` (with `evidence_id`/`source` for citations), `PatientHistory`,
  `Slot`, `SearchResult`.
- **Reference:** `src/hcasst/tools/models.py`.
- **Concepts:** why every clinical fact carries a citation id (grounding /
  zero-hallucination); dataclasses; separating data from behavior.
- **Checkpoint:** Why does each fact have an `evidence_id`? How is this used later
  by the summarizer and the grounding check?

---

# PART 1 — Agentic System Design

## M2 · LLM provider + prompts (the "brain" + the instructions)
- **Build:** an `LLM` interface with two backends — real Anthropic Claude and a
  deterministic **offline MockLLM** chosen automatically; structured prompt
  templates, one per sub-task (planner, summary, disease, grounding).
- **Reference:** `src/hcasst/llm/provider.py`, `src/hcasst/llm/prompts.py`.
- **Concepts:** LLM abstraction/dependency-inversion; `complete` vs
  `complete_json`; prompt engineering; the `[task:NAME]` hint trick so one prompt
  works for both Claude and the mock; temperature=0 for determinism.
- **Checkpoint:** Why a MockLLM at all? How does the app decide Claude vs Mock?
  What is a system vs user prompt? (Part 1 · item 3)

## M3 · Tools (the agent's hands) — booking, records, disease search
- **Build (one tool at a time):**
  - `disease_search` — MedlinePlus + PubMed lookups with an offline KB fallback.
  - `fhir_client` / `records` — patient history (EHR) read + add/update notes.
  - `scheduling` — top-3 slot recommendation + **human-approved** booking (HITL).
- **Reference:** `src/hcasst/tools/disease_search.py`, `fhir_client.py`,
  `records.py`, `scheduling.py`.
- **Concepts:** what a "tool" is in agentic AI; calling external APIs with
  retry/timeout/fallback; **human-in-the-loop** writes (never auto-book);
  trusted medical sources (Medline/WHO/PubMed). (Part 1 · item 2)
- **Checkpoint:** Why must a booking be *proposed* then *confirmed*? What happens
  when the live API is down? Which sources are trusted and why?

## M4 · RAG — embeddings + FAISS vector store + ingest
- **Build:** an `Embedder` (deterministic hashing embedder offline; optional real
  embeddings), a FAISS `VectorStore` (cosine via normalized inner product), and
  `ingest` helpers that turn history/search results into citable documents.
- **Reference:** `src/hcasst/rag/embeddings.py`, `vectorstore.py`, `ingest.py`.
- **Concepts:** embeddings & vector similarity; what RAG is and why it reduces
  hallucination; chunking/documents; cosine similarity. (Part 1 · item 2)
- **Checkpoint:** What is an embedding? Why normalize vectors? How does retrieval
  make answers more grounded? What does FAISS store?

## M5 · Memory module (long-term patient context)
- **Build:** a SQLite-backed memory store + semantic recall over the patient's
  evidence and saved notes; persist summaries/preferences across sessions.
- **Reference:** `src/hcasst/memory/store.py`, `src/hcasst/db/store.py` (memory
  table).
- **Concepts:** short-term vs long-term memory; combining structured storage
  (SQLite) with vector recall; scoping memory per patient. (Part 1 · item 2)
- **Checkpoint:** Difference between RAG retrieval and "memory"? Why store
  summaries back into memory? How is recall kept patient-specific?

## M6 · Planner & goal decomposition
- **Build:** a planner that reads a multi-step request and returns an ordered list
  of `{goal, tool}` steps (intent → sub-goals → tool selection).
- **Reference:** `src/hcasst/agent/planner.py` (+ the planner prompt in M2).
- **Concepts:** goal decomposition; mapping intent to tools; why the planner
  output is structured JSON. (Part 1 · item 1)
- **Checkpoint:** For the CKD sample query, what steps/tools should the planner
  produce? Why decompose instead of one giant prompt?

## M7 · Agent graph (LangGraph state machine)
- **Build:** wire everything into a `StateGraph`:
  `plan → identify patient → route → {summarize | disease | book} → guardrail →
  respond → memory`.
- **Reference:** `src/hcasst/agent/graph.py`.
- **Concepts:** agent orchestration; state machines; nodes vs edges; conditional
  routing; why node names must not collide with state keys. (Part 1 · items 1,3,4)
- **Checkpoint:** What is `AgentState`? How does routing decide which tool node
  runs? Trace the CKD query through the graph node by node.

## M8 · Prompt chaining, summarization & guardrails
- **Build:** the cited-summarization step (RAG → LLM → cited output) and the
  guardrails: citation enforcement + **regenerate-until-grounded** loop (max 3) +
  the HITL write gate.
- **Reference:** `src/hcasst/agent/summarize.py`, `src/hcasst/agent/guardrails.py`.
- **Concepts:** task chaining (retrieve → generate → verify); grounding /
  zero-hallucination; bounded retry loops; citation markers like `[E1]`,
  `[PMID:123]`. (Part 1 · item 3)
- **Checkpoint:** What makes an answer "grounded"? What does the loop do if it
  isn't? Why cap retries at 3?

## M9 · Persistence & observability
- **Build:** the SQLite DAO (appointments, traces, eval, memory) and PHI-masking
  logging + trace recording for each agent step.
- **Reference:** `src/hcasst/db/store.py`, `src/hcasst/obs/logging.py`.
- **Concepts:** persistence; observability/traces; PHI masking & why healthcare
  data needs it. (Part 2 · item 8 foundation)
- **Checkpoint:** What is a trace and why log per step? What is PHI and how is it
  masked in logs?

## M10 · End-to-end golden scenario (the spec's sample flow)
- **Build:** a smoke-test script that runs the CKD query end-to-end and prints the
  plan, cited summary, and booking proposal.
- **Reference:** `scripts/smoke_test.py`.
- **Concepts:** integration testing; the full lifecycle. (Part 1 · item 4)
- **Checkpoint:** Walk the whole flow for: *"My 70-year-old father has chronic
  kidney disease. Book a nephrologist... summarize latest treatments?"*

---

# PART 2 — LLMOps (Evaluation, Monitoring, UI)

## M11 · Model evaluation (QAEval + per-module metrics)
- **Build:** golden eval cases; evaluators — QAEval-style grading of summaries/
  search, citation coverage, tool-selection F1, booking success, grounding; a
  runner that scores all cases, persists results, and prints a summary.
- **Reference:** `src/hcasst/eval/datasets.py`, `evaluators.py`, `runner.py`.
- **Concepts:** LLM-as-judge (QAEvalChain); precision/recall/F1; per-module
  performance logging. (Part 2 · item 6)
- **Checkpoint:** How does QAEval grade an answer? What does tool-F1 measure?
  How is "booking success" defined? Why log per module?

## M12 · Streamlit dashboard (core views)
- **Build:** the multi-page app — assistant/scenario tester, patient & doctor
  views, appointment tracking, latest retrieved medical info.
- **Reference:** `app/streamlit_app.py`, `app/pages/1_Patient_View.py`,
  `2_Appointments.py`, `3_Disease_Info.py`, `app/_shared.py`.
- **Concepts:** Streamlit basics (widgets, state, caching); multipage apps;
  separating UI from logic. (Part 2 · item 7)
- **Checkpoint:** How does the UI call the agent? What does `_shared.py` cache and
  why? How is appointment tracking shown?

## M13 · Evaluation page + Memory/Logs interface
- **Build:** the Evaluation page (run the suite, chart metrics) and the
  Traces/Memory page (planning breakdowns, tool logs, memory traces, scenario
  tester).
- **Reference:** `app/pages/4_Evaluation.py`, `5_Traces.py`.
- **Concepts:** visualizing metrics; surfacing agent reasoning & tool
  success/failure for monitoring. (Part 2 · items 7, 8)
- **Checkpoint:** What do the eval charts tell a reviewer? How do traces help
  debug the agent? How do I demo different scenarios?

---

# STRETCH (reference repo extras — optional, only if I can defend them)

> These go beyond the spec. Build only after Modules 0–13 work and I understand
> them. Each is "QAEval-or-equivalent / memory" done at a higher bar.

- **S1 · Clinical-grade evaluation** — risk-weighted, calibrated metrics
  (faithfulness, clinical safety, composite + release gate) beyond binary QAEval.
  Ref: `src/hcasst/eval/clinical.py`.
- **S2 · Optional external eval backends** — RAGAS/DeepEval as an opt-in,
  online-only, flag-gated supplement. Ref: `src/hcasst/eval/external.py`.
- **S3 · Adaptive memory (Mem0/Zep-style)** — adaptive upsert (dedup/supersede),
  multi-level scoping, recency-weighted recall, progressive consolidation.
  Ref: `src/hcasst/memory/store.py` (advanced parts).

---

# Final deliverables checklist (map to what the institute grades)

- [ ] Working agent that handles the CKD sample flow end-to-end (M10)
- [ ] Planner + goal decomposition (M6, M7) — Part 1 · 1
- [ ] Booking, records/EHR, disease-search tools + FAISS + memory (M3–M5) — Part 1 · 2
- [ ] Structured prompts + task chaining with memory injection (M2, M8) — Part 1 · 3
- [ ] Model evaluation with QAEval/equivalent + per-module logging (M11) — Part 2 · 6
- [ ] Streamlit dashboard: patient/doctor views, appointment tracking, info,
      eval metrics (M12, M13) — Part 2 · 7
- [ ] Memory & logs interface: traces, planning breakdowns, tool logs (M9, M13) — Part 2 · 8
- [ ] `README.md` (how to run) + short design write-up (can reuse/learn from the
      reference `SDD.md`)
- [ ] `NOTES.md` — my own-words explanation of each module (viva prep)
- [ ] I can explain every file and answer follow-up questions

---

## Progress tracker

| Module | Status | My one-line explanation (in NOTES.md) |
| --- | --- | --- |
| M0 Environment | ⬜ | |
| M1 Models | ⬜ | |
| M2 LLM + prompts | ⬜ | |
| M3 Tools | ⬜ | |
| M4 RAG/FAISS | ⬜ | |
| M5 Memory | ⬜ | |
| M6 Planner | ⬜ | |
| M7 Agent graph | ⬜ | |
| M8 Guardrails/summarize | ⬜ | |
| M9 Persistence/obs | ⬜ | |
| M10 Smoke test | ⬜ | |
| M11 Evaluation | ⬜ | |
| M12 Streamlit core | ⬜ | |
| M13 Eval + traces UI | ⬜ | |
| S1 Clinical eval | ⬜ | |
| S2 External eval | ⬜ | |
| S3 Adaptive memory | ⬜ | |
