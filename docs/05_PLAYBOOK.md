# Operations Playbook

**The Operations** — what to do when specific scenarios or problems arise.

## Grounding keeps flagging answers as ungrounded
- **Cause:** the generated answer lacks citation markers, or evidence is too
  sparse to support the claims.
- **Action:** confirm the patient has evidence items; verify the summary prompt
  enforces citations. After 3 attempts the guardrail appends an `[unverified]`
  caveat — this is **by design**, not a failure. In a real deployment, a
  persistent caveat signals "route to a clinician."

## Booking fails with "Unknown proposal"
- **Cause:** the proposal id isn't found in memory or the database.
- **Action:** the scheduler rehydrates proposals from the `appointments` table
  by id (the DB row id *is* the proposal id). Confirm the id matches a row. A
  full restart clears stale in-memory state. If it persists, check that
  `propose_booking` wrote the row before `confirm_booking` was called.

## Disease search returns only [OfflineKB]
- **Cause:** no network, or MedlinePlus/PubMed unreachable.
- **Action:** expected offline behavior — the curated KB is the safe fallback.
  Reconnect the network for live NLM/NCBI sources. Never substitute an
  untrusted source to fill the gap.

## API key exposed or committed
- **Action (immediate):** revoke the key at console.anthropic.com, generate a
  replacement, update `.env`. Confirm `.env` is git-ignored and was never
  committed (`git log --all -- .env`). Rotate before doing anything else.

## Evaluation scores look low
- **Cause:** running offline. The MockLLM returns templated text, so
  `qa_correctness` and `citation_coverage` are near the floor.
- **Action:** set a real key and re-run. Tool-selection F1, booking success, and
  grounding are valid offline; answer-quality metrics need real Claude output.

## Streamlit shows old behavior after a code change
- **Action:** full restart (Ctrl+C, relaunch). Streamlit caches both module
  imports and `@st.cache_resource` objects; a save-triggered rerun does not
  reload them.

## Record change didn't appear / audit empty
- **Cause:** a note was proposed but not confirmed, or the form's pending id was
  lost on a rerun.
- **Action:** re-propose and confirm in one pass. The audit row is written only
  on `confirm_visit`. Check the Doctor view's audit table afterward.

## Routine: back up state
- All durable state lives in `data/hcasst.db` (appointments, audit, traces,
  memory, eval runs). Copy this file to preserve history between sessions or
  before a risky change.

## Routine: reset to a clean demo
- Stop the app, delete `data/hcasst.db` (it is recreated empty on next start),
  restart. Seed patients reload from `data/seed/patients.json`. Use this before
  a fresh graded run so the dashboard starts uncluttered.
