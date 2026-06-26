# Architecture Decision Record (ARD)

**The Strategy** — the architectural rules and constraints that govern the
Agentic Healthcare Assistant, and the reasoning behind them.

## Problem framing

The assistant automates four clinical-support tasks: booking appointments,
managing patient records, retrieving/summarizing history, and searching disease
information. The hard constraints are not features but *risks*: a medical
assistant that hallucinates, writes without oversight, or leaks PHI is worse
than no assistant at all. The architecture is organized around eliminating
those risks.

## Core decisions

### 1. Agent state machine (LangGraph), not a single prompt
The sample query is multi-intent and stateful ("book a nephrologist" **and**
"summarize treatments"). Modeling the agent as a LangGraph state machine makes
each step an inspectable, loggable, guardable node:

    plan -> identify -> route -> {summarize | disease | book} -> guardrail
         -> respond -> memory -> END

A single router loops until every planned tool has run. This same structure is
what makes per-module metrics and tracing possible — the architecture and the
observability requirement are one decision.

### 2. RAG + citation guardrail, not "trust the LLM"
Every clinical statement must carry a citation marker ([E1], [PMID:123],
[MedlinePlus]). The grounding guardrail regenerates an answer up to three times
("loop break of 3") if claims are uncited, then appends an explicit caveat
rather than emit an unverifiable claim. The zero-hallucination bar is therefore
mechanical, not aspirational.

### 3. Offline-first with a deterministic MockLLM
With no API key and no network, the app and its tests still run, deterministically.
This makes the project reproducible for grading and demoable offline. It also
forces a clean, swappable LLM abstraction (Mock <-> Claude) behind one Protocol.

### 4. Human-in-the-loop (HITL) on all writes
The agent *proposes*; a human *confirms*. Bookings and record changes are never
executed autonomously. The gap between `propose_booking` and `confirm_booking`
(and `propose_visit`/`confirm_visit`) is itself the guardrail.

## Quality bars (non-negotiable constraints)

| Bar | Mechanism |
|-----|-----------|
| Zero-hallucination | Citation regex + LLM-judge grounding + regenerate-or-caveat |
| HITL writes | propose -> human confirm -> execute |
| PHI-safe logs | Recursive masking of emails/phones/SSN/DOB before persistence |
| Trusted sources | MedlinePlus (NLM) + PubMed (NCBI) only |
| Reproducibility | Offline-first; deterministic MockLLM; seeded data |

## Guiding principle

**Program to the interface, not the implementation.** The LLM provider, the
embedder, and the disease-search backend each sit behind a stable contract with
two implementations (real and offline/fallback). This is why offline<->online
and mock<->real swap without touching any caller — and it is the single most
load-bearing design idea in the codebase.

## Explicitly deferred (stretch, fenced by design)

- Live FHIR/HL7 read-write (seed-backed records stand in, same return types).
- Mem0/Zep adaptive memory consolidation (simple persistent memory stands in).
- Generative input normalization / OCR for messy intake.

These are deferred deliberately to keep the core defensible, not by omission.
