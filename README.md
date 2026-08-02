# System Design: Support Ticket Automation

Proof-of-concept and system design for an automated support-ticket triage and reply-drafting system. The system classifies incoming tickets, detects PII risk, retrieves relevant knowledge-base answers, and decides whether to auto-close, suggest a draft to an operator, or escalate for full human review — with graceful degradation under load or LLM outages.

## Repository structure

```
System-Design/
├── README.md              # This file
├── AI_USAGE.md            # How AI was used during design/development, what was accepted/rejected
├── SELF_REVIEW.md         # Self-review of the solution: limitations, risks, what's left for production
├── requirements.txt       # Python dependencies for the PoC
├── docs/
│   ├── architecture.md    # System architecture, components, data flow, degradation levels
│   ├── ml.md              # ML/NLP approach: classification, retrieval, thresholds rationale
│   ├── monitoring.md      # Metrics, alerting, audit logging
│   └── risks-and-ops.md   # Risks, PII/compliance handling, operational runbook
└── poc/                   # Working proof-of-concept implementation
    ├── pii.py             # PII/PD detection and risk scoring
    ├── classifier.py      # Topic classification + confidence scoring
    ├── retrieval.py       # TF-IDF cosine-similarity search over the knowledge base
    ├── llm_client.py      # Mock LLM client (draft generation, degradation simulation)
    ├── degradation.py     # Degradation-level logic (L0-L4)
    ├── pipeline.py        # Orchestration: classify -> PII -> retrieval -> decision -> log
    ├── app.py             # FastAPI application exposing the pipeline over HTTP + demo UI
    ├── run_demo.py        # Convenience script to launch the demo (uvicorn)
    ├── data/
    │   ├── mock_tickets.json      # Sample tickets used for demo/testing
    │   └── knowledge_base.json    # Q&A knowledge base used by retrieval.py
    ├── logs/
    │   └── .gitkeep           # decisions.jsonl (audit log) is written here at runtime
    └── static/
        └── index.html         # Minimal web UI for the demo
```

## Quick start

```bash
pip install -r requirements.txt
python poc/run_demo.py
```

Then open http://127.0.0.1:8000 in your browser, or call the API directly:

```bash
# Process all mock tickets
curl http://127.0.0.1:8000/tickets/mock

# Submit a single ticket
curl -X POST http://127.0.0.1:8000/tickets \
  -H "Content-Type: application/json" \
  -d '{"ticket_id": "T100", "text": "Не могу войти в личный кабинет"}'

# View the audit log
curl http://127.0.0.1:8000/decisions
```

## Decision logic (summary)

1. Classify topic + confidence (`classifier.predict`).
2. Detect PII risk (`pii.analyze`) — risk escalates based on combinations of identifying signals, not a bare name alone.
3. Retrieve the most similar knowledge-base entry (`retrieval.find_similar`).
4. Decide the action:
   - **high PII risk** -> retrieval-only draft, always escalated to an operator.
   - **risky topic** (billing/complaint/abuse) -> human-in-the-loop, draft optional.
   - **high confidence + safe** -> auto-close or suggest, depending on the confidence threshold.
   - otherwise -> escalate.
5. Draft generation respects the current degradation level; on LLM errors it falls back to a retrieval-only template.
6. Every decision is appended to `poc/logs/decisions.jsonl` for audit.

See `docs/architecture.md` for the full system design, `docs/ml.md` for the ML/NLP rationale, `docs/risks-and-ops.md` for risk handling and operations, and `docs/monitoring.md` for metrics/alerting. See `AI_USAGE.md` for how AI assistance was used while designing and building this project, and `SELF_REVIEW.md` for a critical self-assessment of the solution.

## Notes

This is a proof-of-concept: the LLM client is mocked, retrieval uses TF-IDF instead of embeddings/vector DB, and PII detection is regex-based. See the docs for the target production architecture.
