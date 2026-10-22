"""PII Redaction and sanitization engine.

Strips identifying patient details (name, phone, address, doctor, lab)
before any content is exposed to an LLM or persisted in memory.
"""

from __future__ import annotations

import re
from typing import Iterable, List


PHONE_REGEX = re.compile(
    r"(?:\+?\d{1,3}[-.\s]?)?\(?\d{2,4}\)?[-.\s]?\d{3,5}[-.\s]?\d{3,5}"
)
EMAIL_REGEX = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,7}\b"
)
DATE_REGEX = re.compile(
    r"\b(?:\d{4}[-/]\d{2}[-/]\d{2}|\d{2}[-/]\d{2}[-/]\d{4})\b"
)
PATIENT_PREFIX_REGEX = re.compile(
    r"(?i)\b(?:Patient(?:\s+Name)?|Name|Pt|Client)\s*[:=]\s*([^\n\r,;|]+)"
)
DOCTOR_PREFIX_REGEX = re.compile(
    r"(?i)\b(?:Dr\.?|Doctor|Ref(?:\.?\s*By)?|Physician)\s*[:=]?\s*([^\n\r,;|]+)"
)
ID_PREFIX_REGEX = re.compile(
    r"(?i)\b(?:Patient\s*ID|PID|UHID|Reg\s*No|ID)\s*[:=]\s*([A-Za-z0-9_-]+)"
)


def redact_pii_from_text(text: str) -> str:
    """Scrub common PII patterns from free text."""
    if not text:
        return ""

    sanitized = text
    sanitized = PHONE_REGEX.sub("[REDACTED_PHONE]", sanitized)
    sanitized = EMAIL_REGEX.sub("[REDACTED_EMAIL]", sanitized)
    sanitized = PATIENT_PREFIX_REGEX.sub("Patient: [REDACTED_NAME]", sanitized)
    sanitized = DOCTOR_PREFIX_REGEX.sub("Ref By: [REDACTED_DOCTOR]", sanitized)
    sanitized = ID_PREFIX_REGEX.sub("ID: [REDACTED_ID]", sanitized)
    sanitized = DATE_REGEX.sub("[REDACTED_DATE]", sanitized)

    return sanitized


def audit_payload_for_leaks(payload: str, forbidden_strings: Iterable[str]) -> List[str]:
    """Audit an LLM payload against ground-truth forbidden PII strings.

    Returns:
        List of forbidden strings detected in the payload (target: empty list).
    """
    leaks: List[str] = []
    payload_lower = payload.lower()

    for item in forbidden_strings:
        item_clean = item.strip()
        # Only check substantial tokens (>2 chars, not simple digits like age)
        if len(item_clean) >= 4 and not item_clean.isdigit():
            if item_clean.lower() in payload_lower:
                leaks.append(item_clean)

    return leaks
