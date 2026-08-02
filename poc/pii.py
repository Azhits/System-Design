"""
PII detection and redaction module.

Key idea: single low-risk signals (e.g. a name alone) are not treated as
high-risk PII. Risk is escalated based on COMBINATIONS of identifying
signals (see risk_level()). This mirrors GDPR/152-FZ style reasoning:
data is 'personal' mainly when it can identify a person, which usually
requires more than a bare name.

This is a PoC-grade implementation: regex-based detectors, no ML/NER.
In the target architecture this would be replaced by a proper PII/NER
service (see docs/ml.md).
"""
import re
from dataclasses import dataclass


PHONE_RE = re.compile(r"(\+?\d[\d\-\s\(\)]{8,}\d)")
EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
CARD_RE = re.compile(r"\b(?:\d[ -]?){13,19}\b")
PASSPORT_SNILS_RE = re.compile(r"\b\d{2,4}[\s-]?\d{6}\b|\b\d{3}-\d{3}-\d{3}\s?\d{2}\b")
ADDRESS_RE = re.compile(r"\b(?:г\.|город|ул\.|улица)\s?[\w\s.]{2,30}\d{1,4}\b", re.IGNORECASE)
NAME_RE = re.compile(r"\b[\u0410-\u042f][\u0430-\u044f]+\s[\u0410-\u042f][\u0430-\u044f]+(?:\s[\u0410-\u042f][\u0430-\u044f]+)?\b")


@dataclass
class PiiSignals:
    name: bool = False
    phone: bool = False
    email: bool = False
    card_number: bool = False
    passport_snils: bool = False
    address: bool = False

    def any_identifier(self) -> bool:
        return any([self.phone, self.email, self.card_number, self.address])


def detect_signals(text: str) -> PiiSignals:
    return PiiSignals(
        name=bool(NAME_RE.search(text)),
        phone=bool(PHONE_RE.search(text)),
        email=bool(EMAIL_RE.search(text)),
        card_number=bool(CARD_RE.search(text)),
        passport_snils=bool(PASSPORT_SNILS_RE.search(text)),
        address=bool(ADDRESS_RE.search(text)),
    )


def risk_level(signals: PiiSignals) -> str:
    """
    high_pii: card number OR passport/SNILS OR (name AND another identifier)
    low_pii: a single weak signal (name only, or email/phone alone)
    none: no PII signals detected
    """
    if signals.card_number or signals.passport_snils:
        return "high_pii"
    if signals.name and signals.any_identifier():
        return "high_pii"
    if signals.name or signals.phone or signals.email or signals.address:
        return "low_pii"
    return "none"


def redact(text: str) -> str:
    """Mask sensitive substrings before sending text to an external LLM API."""
    text = CARD_RE.sub("[CARD_REDACTED]", text)
    text = PASSPORT_SNILS_RE.sub("[ID_REDACTED]", text)
    text = EMAIL_RE.sub("[EMAIL_REDACTED]", text)
    text = PHONE_RE.sub("[PHONE_REDACTED]", text)
    text = ADDRESS_RE.sub("[ADDRESS_REDACTED]", text)
    return text


def analyze(text: str) -> dict:
    signals = detect_signals(text)
    level = risk_level(signals)
    return {
        "risk_level": level,
        "signals": signals.__dict__,
        "redacted_text": redact(text),
    }
