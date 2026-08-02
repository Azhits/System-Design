# Architecture

## Overview

The system automates first-line support-ticket handling: classify the ticket, check for PII/PD risk, retrieve a relevant knowledge-base answer, and decide between auto-close, operator-assisted suggestion, or full escalation. Every decision is logged for audit and compliance.

```
        +-------------+     +-------------+     +--------------+
        |  Classifier |     |  PII/PD     |     |  Retrieval   |
 Ticket ->  (topic +   | --> |  detector   | --> |  (KB search) |
        |  confidence)|     |  (risk lvl) |     |              |
        +-------------+     +-------------+     +--------------+
               \                  |                    |
                \                 v                    v
                 +-----------> Decision engine <-------+
                                    |
                        +-----------+-----------+
                        |           |           |
                   auto_close    suggest     escalate
                        |           |           |
                        +-----------+-----------+
                                    |
                              audit log (jsonl)
```

## Components

- **classifier.py** — topic classification (TF-IDF + Decision Tree in the PoC). Returns topic + confidence.
- **pii.py** — PII/PD signal detection and risk scoring. In the PoC this is regex-based; production should use a proper PII/NER service.
- **retrieval.py** — finds the most relevant knowledge-base entry via TF-IDF cosine similarity (PoC). Target architecture: sentence embeddings + a vector DB (pgvector/FAISS).
- **llm_client.py** — abstraction over the LLM provider used for draft generation. The PoC uses a mock client with configurable failure/latency flags so the rest of the pipeline can be tested against degraded conditions without a real API.
- **degradation.py** — computes the current degradation level (L0-L4) from queue size and LLM health, and tells the pipeline whether to use the LLM, batch requests, or skip straight to escalation.
- **pipeline.py** — orchestrates the above steps and applies the decision logic (see `ml.md` and `risks-and-ops.md`).
- **app.py** — FastAPI HTTP interface + demo UI, so the pipeline can be exercised without writing code.

## Data flow

1. A ticket (`ticket_id`, `text`) arrives via the API (or is read from `data/mock_tickets.json`).
2. The classifier assigns a topic and confidence score.
3. The PII module scores the risk level from combinations of identifying signals found in the text.
4. The retrieval module finds the closest knowledge-base entry to use as context.
5. The pipeline applies the decision rules and, if needed, calls the LLM (respecting the current degradation level) to draft a reply.
6. The final decision (action, draft, confidence, risk, degradation level, latency) is appended to `logs/decisions.jsonl`.

## Degradation levels (L0-L4)

| Level | Trigger | Behavior |
|-------|---------|----------|
| L0 | normal load | Full LLM generation per ticket with retrieval context |
| L1 | high load | LLM used in micro-batches (multiple tickets per API call) to control cost/latency |
| L2 | LLM overloaded/slow | No LLM calls; retrieval-only template drafts |
| L3 | LLM unavailable (circuit breaker open) | Retrieval-only drafts, same as L2 |
| L4 | critical overload | No draft generation at all; everything routed straight to an operator |

This ensures the system keeps functioning (with reduced automation quality) instead of failing outright when the LLM provider is degraded or the ticket queue spikes.

## Target production architecture (beyond the PoC)

- Replace the TF-IDF classifier with a model trained on real historical ticket data (or a fine-tuned/prompted LLM classifier with a fallback).
- Replace TF-IDF retrieval with sentence embeddings + a vector database (pgvector or FAISS) for semantic search over a larger knowledge base.
- Replace the mock LLM client with a real provider client behind a circuit breaker, plus request/response logging for auditability.
- Move the audit log from a local `.jsonl` file to a proper data store (e.g. PostgreSQL or an append-only event log) with retention policy aligned to `docs/risks-and-ops.md`.
- Add authentication/authorization to the API and role-based access for operators reviewing escalated tickets.
