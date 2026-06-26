# User Guide

**The Daily Use** — how to operate the dashboard, view by view.

The sidebar has a backend badge, an optional API-key field, and a **View**
selector with six entries.

## Assistant

The scenario tester — the heart of the demo.

1. Select a **patient**.
2. Pick an **example** request, or type your own.
3. Click **Run assistant**.
4. Read the results:
   - **Plan** — the tools the agent chose, in order, each marked done.
   - **Response** — the assembled answer (summary, proposed booking, cited
     disease info).
   - **Guardrail / grounding verdict** (expander) — whether the answer passed
     the zero-hallucination check.
   - **Evidence & sources** (expander) — the [E#]/[M#] citations and external
     sources used.
5. If a booking is proposed, click **Approve & book** (human-in-the-loop) — only
   then is it scheduled. **Reject** discards it.

## Patient

- **Medical history** — the patient's structured + unstructured record.
- **Manage record (add / update)** — the human-in-the-loop write flow:
  1. Choose a **kind** (`note` = unstructured; `observation`/`condition`/etc =
     structured).
  2. To **update**, enter an existing evidence id (e.g. `E1`); leave blank to
     **add**.
  3. Type the text, click **Propose record change**, then **Confirm**.
- **Appointments** — this patient's bookings.

## Doctor

- **Appointment tracking** — all appointments with status
  (proposed / scheduled / confirmed / completed / cancelled / rejected) and a
  status bar chart.
- **Record-change audit** — who changed what, when (populated after you confirm
  a record change).

## Evaluation

- Click **Run evaluation** to score the agent over the golden cases.
- See per-metric bars (tool selection F1, booking success, citation coverage,
  QA correctness) and the **OVERALL** score.
- Offline, QA/citation scores are low by design (the MockLLM returns templated
  text); run with a real key for representative numbers.

## Traces

- Enter a session id (or leave blank for the latest) to see the **node-by-node
  trace**: plan -> tools -> guardrail -> respond, including the
  `human_approval_gate | blocked` row that proves HITL fired.
- A tool success/failure chart. Patient data in payloads is masked (PHI-safe).

## Documentation

- This hub. Use the dropdown to read the ARD, Technical Spec, Implementation
  Guide, User Guide, and Playbook.

## Switching to real Claude

Sidebar -> paste an API key -> **Apply key**. Blank reverts to the offline mock.
