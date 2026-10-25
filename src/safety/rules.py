"""Deterministic forbidden words scanner for English and Hindi text.

Enforces Core Principle #3:
- Never diagnose, name a condition the user 'has', mention medicines, doses,
  treatments, supplements to take, or give diet/lifestyle prescriptions.
- Never say a result is 'fine', 'serious', 'critical', or 'nothing to worry about'.

Scans text using compiled regex patterns with word boundaries. Rejects any LLM output
that contains forbidden terms, triggering an immediate fallback to deterministic kb_template.
"""

from __future__ import annotations

import re
from typing import NamedTuple


class ForbiddenMatch(NamedTuple):
    pattern_name: str
    matched_text: str
    start: int
    end: int


# English forbidden patterns (case-insensitive with word boundary enforcement)
FORBIDDEN_ENGLISH_PATTERNS: dict[str, re.Pattern] = {
    # 1. Diagnostic phrases / Attributing conditions to user
    "diagnosis_you_have": re.compile(r"\byou\s+have\b", re.IGNORECASE),
    "diagnosis_diagnosed_with": re.compile(r"\bdiagnosed\s+with\b", re.IGNORECASE),
    "diagnosis_suffer_from": re.compile(r"\bsuffer(?:ing)?\s+from\b", re.IGNORECASE),
    "diagnosis_you_suffer": re.compile(r"\byou\s+suffer\b", re.IGNORECASE),
    "diagnosis_you_are_suffering": re.compile(r"\byou\s+are\s+suffering\b", re.IGNORECASE),
    "diagnosis_you_contracted": re.compile(r"\byou\s+contracted\b", re.IGNORECASE),
    "diagnosis_you_might_have": re.compile(r"\byou\s+(?:might|probably|likely)\s+have\b", re.IGNORECASE),

    # 2. Prescriptions, Medicines, Dosages & Treatments
    # Note: \btake\b is forbidden when directing user action (e.g., "take this", "take aspirin", "take 5mg")
    "prescription_take_meds": re.compile(
        r"\btake\s+(?:this|these|medication|medicine|tablets?|capsules?|pills?|supplements?|drugs?|\d+)\b",
        re.IGNORECASE,
    ),
    "prescription_prescribed": re.compile(r"\bprescribed?\b", re.IGNORECASE),
    "prescription_prescription": re.compile(r"\bprescription\b", re.IGNORECASE),
    # Dosage in mg (e.g. '500 mg', but NOT concentration units like 'mg/dL' or 'mg/L')
    "prescription_mg_dosage": re.compile(r"\b\d+\s*mg\b(?!\s*[/])", re.IGNORECASE),
    "prescription_tablet": re.compile(r"\btablets?\b", re.IGNORECASE),
    "prescription_capsule": re.compile(r"\bcapsules?\b", re.IGNORECASE),
    "prescription_pill": re.compile(r"\bpills?\b", re.IGNORECASE),
    "prescription_dosage": re.compile(r"\bdosages?\b", re.IGNORECASE),
    "prescription_dose": re.compile(r"\bdoses?\b", re.IGNORECASE),
    "prescription_cure": re.compile(r"\bcure[sd]?\b|\bcuring\b", re.IGNORECASE),
    "prescription_treat_imperative": re.compile(r"\btreat(?:ing|ment)?\b", re.IGNORECASE),

    # 3. False reassurance & alarm words
    "reassurance_fine": re.compile(r"\bfine\b", re.IGNORECASE),
    "reassurance_normal_and_healthy": re.compile(r"\bnormal\s+and\s+healthy\b", re.IGNORECASE),
    "alarm_serious": re.compile(r"\bserious\b", re.IGNORECASE),
    "alarm_critical": re.compile(r"\bcritical\b", re.IGNORECASE),
    "reassurance_nothing_to_worry_about": re.compile(r"\bnothing\s+to\s+worry\s+about\b", re.IGNORECASE),
    "reassurance_dont_worry": re.compile(r"\bdon'?t\s+worry\b", re.IGNORECASE),
    "alarm_danger": re.compile(r"\bdanger(?:ous)?\b", re.IGNORECASE),
    "alarm_life_threatening": re.compile(r"\blife-?threatening\b", re.IGNORECASE),
    "reassurance_no_concern": re.compile(r"\bno\s+concern\b", re.IGNORECASE),
    "reassurance_completely_safe": re.compile(r"\bcompletely\s+safe\b", re.IGNORECASE),
}

# Hindi forbidden patterns (Devanagari scripts and transliterations)
FORBIDDEN_HINDI_PATTERNS: dict[str, re.Pattern] = {
    # 1. Diagnostic phrases
    "hi_diagnosis_you_have_disease": re.compile(r"आपको\s+(?:बीमारी|रोग|समस्या)\s+है", re.IGNORECASE),
    "hi_diagnosis_diagnosed": re.compile(r"निदान\s+किया\s+गया", re.IGNORECASE),
    "hi_diagnosis_suffering": re.compile(r"आप\s+पीड़ित\s+हैं", re.IGNORECASE),
    "hi_diagnosis_you_have": re.compile(r"आपको\s+है", re.IGNORECASE),

    # 2. Prescriptions, Medicines, Dosages
    "hi_prescription_take_medicine": re.compile(
        r"(?:दवा|दवाई|औषधि)\s+(?:लें|लेना|लेनी|लीजिए|खाइए|खानी|खाएं)", re.IGNORECASE
    ),
    "hi_prescription_tablet": re.compile(r"गोल(?:ी|ियां)", re.IGNORECASE),
    "hi_prescription_capsule": re.compile(r"कैप्सूल", re.IGNORECASE),
    "hi_prescription_dosage": re.compile(r"खुराक", re.IGNORECASE),
    "hi_prescription_cure": re.compile(r"इलाज|उपचार", re.IGNORECASE),

    # 3. False reassurance & alarm words
    "hi_reassurance_nothing_to_worry": re.compile(r"चिंता\s+की\s+कोई\s+बात\s+नहीं", re.IGNORECASE),
    "hi_reassurance_dont_worry": re.compile(r"चिंता\s+(?:मत\s+करो|न\s+करें|मत\s+कीजिए)", re.IGNORECASE),
    "hi_reassurance_all_fine": re.compile(r"सब\s+ठीक\s+है", re.IGNORECASE),
    "hi_reassurance_completely_normal": re.compile(r"बिल्कुल\s+(?:सामान्य|ठीक)", re.IGNORECASE),
    "hi_alarm_danger": re.compile(r"खतरा|खतरनाक", re.IGNORECASE),
    "hi_alarm_serious": re.compile(r"गंभीर", re.IGNORECASE),
}

ALL_FORBIDDEN_PATTERNS: dict[str, re.Pattern] = {
    **FORBIDDEN_ENGLISH_PATTERNS,
    **FORBIDDEN_HINDI_PATTERNS,
}


def scan_for_forbidden_terms(text: str) -> list[ForbiddenMatch]:
    """Scan input text against all forbidden diagnostic, treatment, and alarm patterns.

    Args:
        text: String to scan (e.g. LLM-generated explanation).

    Returns:
        List of ForbiddenMatch namedtuples representing any rule violations.
    """
    if not text:
        return []

    matches: list[ForbiddenMatch] = []
    for name, pattern in ALL_FORBIDDEN_PATTERNS.items():
        for m in pattern.finditer(text):
            matches.append(
                ForbiddenMatch(
                    pattern_name=name,
                    matched_text=m.group(0),
                    start=m.start(),
                    end=m.end(),
                )
            )
    return matches


def is_safe_explanation(text: str) -> tuple[bool, list[str]]:
    """Verify whether an explanation text complies with strict medical safety rules.

    Args:
        text: Explanation text.

    Returns:
        Tuple of (is_safe: bool, violation_descriptions: list[str]).
    """
    matches = scan_for_forbidden_terms(text)
    if not matches:
        return True, []

    violations = [f"Forbidden term '{m.matched_text}' (rule: {m.pattern_name})" for m in matches]
    return False, violations
