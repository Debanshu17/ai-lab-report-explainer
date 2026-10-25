"""Safety layer for AI Lab Report Explainer.

Enforces strict non-diagnostic boundaries, regex scanning for forbidden terms,
disclaimer injections, and out-of-scope query rejection.
"""

from src.safety.rules import (
    scan_for_forbidden_terms,
    is_safe_explanation,
    FORBIDDEN_ENGLISH_PATTERNS,
    FORBIDDEN_HINDI_PATTERNS,
)
from src.safety.disclaimers import (
    get_disclaimer,
    get_urgent_care_footer,
    requires_urgent_care_footer,
    EDUCATIONAL_DISCLAIMER_EN,
    EDUCATIONAL_DISCLAIMER_HI,
)
from src.safety.scope import is_question_in_scope, CANNED_OUT_OF_SCOPE_MESSAGE

__all__ = [
    "scan_for_forbidden_terms",
    "is_safe_explanation",
    "FORBIDDEN_ENGLISH_PATTERNS",
    "FORBIDDEN_HINDI_PATTERNS",
    "get_disclaimer",
    "get_urgent_care_footer",
    "requires_urgent_care_footer",
    "EDUCATIONAL_DISCLAIMER_EN",
    "EDUCATIONAL_DISCLAIMER_HI",
    "is_question_in_scope",
    "CANNED_OUT_OF_SCOPE_MESSAGE",
]
