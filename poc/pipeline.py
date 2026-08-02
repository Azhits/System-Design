"""
Pipeline orchestration: classify -> risk/PII -> retrieval -> draft/escalate -> log.

Decision logic (see docs/ml.md for thresholds rationale):
  1. Classify topic + confidence via classifier.predict()
  2. Detect PII risk via pii.analyze()
  3. Retrieve most similar KB item via retrieval.find_similar()
  4. Decide action:
     - high_pii                      -> ALWAYS retrieval-only draft, escalate to operator
     - risky topic OR low confidence -> escalate to operator (with or without draft)
     - high confidence + safe        -> auto_close or suggest depending on threshold
  5. Draft generation respects the current degradation level (L0-L4)
  6. Every decision is appended to logs/decisions.jsonl for audit
"""
import json
import time
from pathlib import Path
from datetime import datetime, timezone

from . import classifier
from . import retrieval
from . import pii
from . import degradation
from .llm_client import LLMClient, retrieval_only_draft

LOG_PATH = Path(__file__).parent / "logs" / "decisions.jsonl"

CONFIDENCE_AUTO = 0.75
CONFIDENCE_SUGGEST = 0.50


def _log_decision(record: dict) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _build_decision_trace(
    topic: str,
    confidence: float,
    risk: str,
    pii_signals: dict,
    deg: dict,
    action: str,
    degradation_note: str,
    similar: list,
) -> list[str]:
    """Build a human-readable list of reasons for the final decision."""
    trace = []
    trace.append(f"topic={topic}, confidence={round(confidence, 3)}")

    active_signals = [k for k, v in pii_signals.items() if v]
    if risk == "high_pii":
        trace.append(f"high_pii_detected: {' + '.join(active_signals) if active_signals else 'card/passport'}")
        trace.append("high_pii -> LLM_skipped, retrieval_only_draft, action=escalate")
    elif risk == "low_pii":
        trace.append(f"low_pii_detected: {' + '.join(active_signals)}")

    if not deg["llm_available"] and deg["level"] in ("L0", "L1", "L3"):
        trace.append("llm_available=false -> forced degradation >= L3")

    deg_level = deg["level"]
    queue_size = deg["queue_size"]
    if deg_level != "L0":
        trace.append(f"queue_size={queue_size} -> degradation={deg_level} ({deg['label']})")

    if degradation_note and "fallback" in degradation_note:
        trace.append("llm_error_caught -> switched to retrieval_fallback")

    if similar:
        trace.append(f"retrieval: kb_id={similar[0]['kb_id']}, similarity={round(similar[0]['similarity'], 3)}")

    trace.append(f"action={action}")
    return trace


def process_ticket(ticket: dict, queue_size: int = 0, llm_available: bool = True) -> dict:
    """
    Main entry point. `ticket` must have 'ticket_id' and 'text'.
    Returns a decision record (also appended to the audit log).
    """
    start = time.monotonic()
    text = ticket["text"]

    # Step 1: fast classification (hot path, rule/ML based, no LLM dependency)
    cls_result = classifier.predict(text)
    topic = cls_result["topic"]
    confidence = cls_result["confidence"]

    # Step 2: PII detection (always local, no external calls)
    pii_result = pii.analyze(text)
    risk = pii_result["risk_level"]
    pii_signals = pii_result["signals"]
    redacted_text = pii_result["redacted_text"]

    # Step 3: retrieval of similar KB entry (used both for LLM context and fallback)
    similar = retrieval.find_similar(text, top_k=1)
    context_snippet = similar[0]["answer"] if similar else ""

    # Step 4: degradation level for this request
    deg = degradation.get_level(queue_size=queue_size, llm_available=llm_available)

    action = None
    draft = None
    requires_human = False
    degradation_note = deg["label"]

    if risk == "high_pii":
        # High PII: LLM is never used, only retrieval-based template.
        # Always escalated to an operator for manual review before any
        # further LLM usage is allowed (see docs/risks-and-ops.md).
        draft = retrieval_only_draft(context_snippet)
        action = "escalate"
        requires_human = True
    elif cls_result["is_risky_topic"]:
        # Risky topic (billing/complaint/abuse): human-in-the-loop required.
        # A draft MAY be produced to help the operator, but never auto-sent.
        try:
            if deg["use_llm"]:
                draft = LLMClient.generate_draft(text, context_snippet, topic)
            else:
                draft = retrieval_only_draft(context_snippet)
        except (ConnectionError, TimeoutError):
            draft = retrieval_only_draft(context_snippet)
            degradation_note += "+llm_error_fallback"
        action = "escalate"
        requires_human = True
    elif deg["escalate_only"]:
        # Critical overload: no draft generation at all, straight to operator queue.
        action = "escalate"
        requires_human = True
    elif confidence >= CONFIDENCE_AUTO:
        try:
            if deg["use_llm"]:
                draft = LLMClient.generate_draft(text, context_snippet, topic)
            else:
                draft = retrieval_only_draft(context_snippet)
        except (ConnectionError, TimeoutError):
            draft = retrieval_only_draft(context_snippet)
            degradation_note += "+llm_error_fallback"
        action = "auto_close"
    elif confidence >= CONFIDENCE_SUGGEST:
        try:
            if deg["use_llm"]:
                draft = LLMClient.generate_draft(text, context_snippet, topic)
            else:
                draft = retrieval_only_draft(context_snippet)
        except (ConnectionError, TimeoutError):
            draft = retrieval_only_draft(context_snippet)
            degradation_note += "+llm_error_fallback"
        action = "suggest"
        requires_human = True
    else:
        action = "escalate"
        requires_human = True

    latency_ms = round((time.monotonic() - start) * 1000, 2)

    decision_trace = _build_decision_trace(
        topic=topic,
        confidence=confidence,
        risk=risk,
        pii_signals=pii_signals,
        deg=deg,
        action=action,
        degradation_note=degradation_note,
        similar=similar,
    )

    record = {
        "ticket_id": ticket.get("ticket_id"),
        "text": text,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "topic": topic,
        "confidence": round(confidence, 3),
        "pii_risk": risk,
        "pii_signals": pii_signals,
        "redacted_text": redacted_text,
        "action": action,
        "requires_human": requires_human,
        "draft": draft,
        "decision_trace": decision_trace,
        "similar_kb_id": similar[0]["kb_id"] if similar else None,
        "similarity": similar[0]["similarity"] if similar else None,
        "degradation_level": deg["level"],
        "degradation_note": degradation_note,
        "llm_available": llm_available,
        "latency_ms": latency_ms,
        "model_version": "poc-tfidf-tree-v1",
    }
    _log_decision(record)
    return record
