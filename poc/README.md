# Support Ticket Automation - PoC

Proof-of-concept for an automated support-ticket triage and reply-drafting pipeline. It classifies incoming tickets, checks for PII risk, retrieves a similar knowledge-base answer, and decides whether to auto-close, suggest a draft to an operator, or escalate for full human review. All decisions are logged for audit, and the system degrades gracefully (L0-L4) when the LLM is slow, unavailable, or the queue is overloaded.

## Structure

```
poc/
├── pii.py            # PII/PD detection and risk scoring (regex-based, no ML/NER)
├── classifier.py     # Topic classification + confidence scoring
├── retrieval.py      # TF-IDF cosine-similarity search over the knowledge base
├── llm_client.py     # Mock LLM client (draft generation, degradation simulation)
├── degradation.py     # Degradation-level logic (L0-L4) based on queue size / LLM health
├── pipeline.py       # Orchestration: classify -> PII -> retrieval -> decision -> log
├── app.py            # FastAPI application exposing the pipeline over HTTP + demo UI
├── run_demo.py       # Convenience script to launch the demo (uvicorn)
├── data/
│   ├── mock_tickets.json     # Sample tickets used for demo/testing
│   └── knowledge_base.json   # Q&A knowledge base used by retrieval.py
├── logs/
│   └── .gitkeep       # decisions.jsonl (audit log) is written here at runtime
└── static/
    └── index.html     # Minimal web UI for the demo
```

## Quick start

```bash
pip install -r requirements.txt
python poc/run_demo.py
```

Then open http://127.0.0.1:8000 in your browser, or use the API directly:

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

## Decision logic

1. Classify topic + confidence (`classifier.predict`).
2. Detect PII risk (`pii.analyze`) - risk escalates based on combinations of identifying signals, not a bare name alone.
3. Retrieve the most similar knowledge-base entry (`retrieval.find_similar`).
4. Decide the action:
   - **high PII risk** -> retrieval-only draft, always escalated to an operator.
   - **risky topic** (billing/complaint/abuse) -> human-in-the-loop, draft optional.
   - **high confidence + safe** -> auto-close or suggest, depending on the confidence threshold.
   - otherwise -> escalate.
5. Draft generation respects the current degradation level; on LLM errors it falls back to a retrieval-only template.
6. Every decision is appended to `logs/decisions.jsonl` for audit.

## Notes

This is a proof-of-concept: the LLM client is mocked, retrieval uses simple TF-IDF instead of embeddings/vector DB, and PII detection is regex-based. See the project's design docs for the target production architecture.
