# Technical Specification

**The Construction** — how the software is built.

## Stack

- **Python 3.11**, **Pydantic v2** (typed models + boundary validation)
- **LangGraph** (agent orchestration as a state machine)
- **langchain-anthropic** (Claude provider)
- **FAISS** (vector store, IndexFlatIP) + **sentence-transformers**
  (all-MiniLM-L6-v2, 384-dim embeddings)
- **SQLite** (persistence: appointments, record_audit, traces, memory, eval_runs)
- **Streamlit** + **Plotly** (dashboard)
- **httpx** (MedlinePlus / PubMed E-utilities)

## Module map

    config/settings.py        Central config; offline switch (llm_available)
    src/hcasst/
      models.py               Patient, EvidenceItem, PatientHistory, Slot, SearchResult
      llm/
        provider.py           LLM Protocol; ClaudeLLM + MockLLM; get_llm() switch
        prompts.py            One structured prompt per task ([task:NAME] tags)
      tools/
        scheduling.py         HITL booking; synthetic slots + provider roster
        records.py            EHR add/update (structured + unstructured), HITL
        disease_search.py     MedlinePlus + PubMed live; offline KB fallback
      rag/
        embeddings.py         Embedder Protocol; SentenceTransformer + Hashing
        vectorstore.py        FAISS IndexFlatIP; Document/Retrieved models
        ingest.py             history/search -> citable Documents
      memory/store.py         Long-term context: durable write + semantic recall
      agent/
        state.py              AgentState TypedDict; PlanStep
        planner.py            Decompose query -> validated tool plan
        graph.py              LangGraph wiring; HealthAssistant facade
        guardrails.py         Citation check + grounding + regenerate-or-caveat
        summarize.py          Cited summary + disease synthesis (RAG + grounding)
      eval/
        evaluators.py         qa_correctness, citation_coverage, tool_f1, booking
        datasets.py           Golden cases (CKD, afib, summary-only, disease-only)
        runner.py             Run + score + persist to eval_runs
      db/store.py             SQLite DAO (parameterized, injection-safe)
      obs/logging.py          PHI masking (mask_phi / mask_obj)
    app/streamlit_app.py      Dashboard (6 views)

## Data contracts

Every tool returns a typed Pydantic model. Every clinical fact is an
`EvidenceItem` whose `evidence_id` is validated against `E\d+`. Citations travel
*with* the data, so the summarizer can cite and the guardrail can verify.

## Agent flow

`plan -> identify -> route` then a conditional router loops
`route <-> {summarize | disease | book}` until the plan is exhausted, then
`guardrail -> respond -> memory -> END`. Routing is pure logic over the plan and
an `executed` set; the LLM never decides control flow at runtime.

## LLM abstraction

`LLM` is a Protocol with `complete()` and `complete_json()`. `ClaudeLLM` calls
the API; `MockLLM` reads the `[task:NAME]` tag in the system prompt and returns
a deterministic, valid response per task. `get_llm()` selects based on
`settings.llm_available`. The planner pins an output schema so both backends
return the same shape.

## Persistence schema (SQLite)

- `appointments(id, patient_id, ..., status, created_at)`
- `record_audit(id, patient_id, action, evidence_id, kind, content, author, ...)`
- `traces(id, session_id, step, name, status, payload, created_at)` — PHI-masked
- `memory(id, patient_id, kind, content, scope, status, importance, created_at)`
- `eval_runs(id, run_id, module, metric, value, detail, created_at)`

## Coding standards

- Type hints throughout; validation at boundaries via Pydantic.
- Parameterized SQL only (no string interpolation into queries).
- Graceful degradation: every external dependency has an offline fallback.
- Decorators where they earn their place (`@property`, `@classmethod`,
  `@field_validator`, `@lru_cache`, `@staticmethod`).
