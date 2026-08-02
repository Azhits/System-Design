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

Regex design notes (false-positive prevention):
  PHONE_RE  - Russian mobile/landline formats only. Requires explicit
              country code (+7 / 8) OR parenthesised area code, so bare
              digit sequences like SNILS (123-456-789 00) and passport
              numbers (4510 123456) are NOT matched.
  CARD_RE   - 13-19 contiguous digit groups with optional single-char
              separators, but PASSPORT_SNILS_RE is applied FIRST in
              detect_signals so passport 'XXXX XXXXXX' (10 digits) is
              handled by the dedicated pattern and not misclassified.
              Card numbers are at least 13 digits; passport series+number
              is exactly 10 digits, so they don't overlap.
"""
import re
from dataclasses import dataclass


# Phone: must start with +7, 8, or have area code in parentheses.
# Matches: +7 921 555-12-34 | 8(495)123-45-67 | +79215551234
# Does NOT match: bare digit sequences such as SNILS or passport numbers.
PHONE_RE = re.compile(
    r"(?:"
    r"(?:\+7|8)[\s\-]?[\(]?\d{3}[\)]?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}"
    r"|\+7\d{10}"
    r")"
)

EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")

# Card: 13-19 digits with optional spaces/dashes between groups of 4.
# Uses word boundaries to avoid matching inside longer digit strings.
CARD_RE = re.compile(
    r"\b(?:\d{4}[\s\-]?){3}\d{1,7}\b"
)

# Passport: 4-digit series + 6-digit number (with optional space/dash)
# SNILS: NNN-NNN-NNN NN or NNNNNNNNNNN (11 digits)
PASSPORT_SNILS_RE = re.compile(
    r"\b\d{4}[\s]\d{6}\b"            # passport: 4510 123456
    r"|\b\d{3}-\d{3}-\d{3}\s?\d{2}\b"  # SNILS:    123-456-789 00
    r"|\b\d{11}\b"                       # SNILS without separators: 12345678900
)

ADDRESS_RE = re.compile(
    r"\b(?:\u0433\.|\u0433\u043e\u0440\u043e\u0434|"
    r"\u0443\u043b\.|\u0443\u043b\u0438\u0446\u0430)"
    r"\s?[\w\s.]{2,30}\d{1,4}\b",
    re.IGNORECASE,
)
NAME_RE = re.compile(
    r"\b[\u0410-\u042f][\u0430-\u044f]+\s"
    r"[\u0410-\u042f][\u0430-\u044f]+"
    r"(?:\s[\u0410-\u042f][\u0430-\u044f]+)?\b"
)


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
    # Run PASSPORT_SNILS_RE before CARD_RE/PHONE_RE so the dedicated
    # pattern claims its digit sequences first (no double-counting).
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
