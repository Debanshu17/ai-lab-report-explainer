"""Follow-up Q&A scope restriction.

Enforces scope boundaries:
Rejects queries outside the scope of the tests present in the current report
(e.g., unrelated clinical symptoms, requests for medication, or non-lab questions)
with a canned response BEFORE any LLM call is made.
"""

from __future__ import annotations

import re
from typing import Optional, Sequence

from src.data.mapping import AliasResolver, normalize_alias
from src.kb.alias import get_default_resolver

CANNED_OUT_OF_SCOPE_MESSAGE = (
    "This educational tool only explains the specific blood tests present on your uploaded report "
    "and general laboratory reference concepts. It cannot evaluate unrelated symptoms, diagnose conditions, "
    "or recommend medications. Please discuss your symptoms, diagnosis, and treatment options directly with "
    "your healthcare provider."
)

# Symptoms, body parts, and medical inquiries unrelated to blood tests
UNRELATED_SYMPTOM_PATTERNS = [
    re.compile(r"\b(?:knee|back|ankle|shoulder|elbow|wrist|hip|foot|toe|tooth|teeth|ear|eye|skin\s+rash)\b", re.IGNORECASE),
    re.compile(r"\b(?:fracture|broken\s+bone|sprain|bruise|cut|wound|burn)\b", re.IGNORECASE),
    re.compile(r"\b(?:cough|sneez|runny\s+nose|sore\s+throat|congestion|cold|flu)\b", re.IGNORECASE),
    re.compile(r"\b(?:headache|migraine)\b", re.IGNORECASE),
]

# Prescriptive and medication seeking patterns
MEDICATION_SEEKING_PATTERNS = [
    re.compile(r"\bshould\s+i\s+(?:take|use|drink|eat)\b", re.IGNORECASE),
    re.compile(r"\bwhat\s+(?:medicine|drug|tablet|pill|medication|supplement)\b", re.IGNORECASE),
    re.compile(r"\bhow\s+much\s+(?:dosage|dose|mg)\b", re.IGNORECASE),
    re.compile(r"\bcan\s+you\s+prescribe\b", re.IGNORECASE),
]

# Educational lab topics that are always in scope
GENERAL_LAB_TOPICS = [
    "reference range",
    "range",
    "fasting",
    "fast",
    "lab",
    "laboratory",
    "doctor",
    "physician",
    "test",
    "blood",
    "report",
    "result",
    "sample",
    "specimen",
    "fluctuate",
    "vary",
    "unit",
]


def is_question_in_scope(
    question: str,
    report_tests: Sequence[str],
    resolver: Optional[AliasResolver] = None,
) -> tuple[bool, str]:
    """Check whether a user's follow-up question is strictly within scope.

    Args:
        question: Patient's free-text question.
        report_tests: List of test names or test_ids present in the patient's report.
        resolver: AliasResolver instance (defaults to singleton).

    Returns:
        tuple[bool, str]: (is_in_scope, message_or_reason).
            If False, message is CANNED_OUT_OF_SCOPE_MESSAGE.
    """
    clean_q = question.strip()
    if not clean_q:
        return False, CANNED_OUT_OF_SCOPE_MESSAGE

    # 1. Reject questions seeking medications, prescriptions, or dosages
    for pat in MEDICATION_SEEKING_PATTERNS:
        if pat.search(clean_q):
            return False, CANNED_OUT_OF_SCOPE_MESSAGE

    # 2. Reject questions describing unrelated anatomical or physical symptoms
    for pat in UNRELATED_SYMPTOM_PATTERNS:
        if pat.search(clean_q):
            return False, CANNED_OUT_OF_SCOPE_MESSAGE

    # 3. Check for mentions of tests present on the user's report
    norm_q = normalize_alias(clean_q)
    r = resolver or get_default_resolver()

    # Collect all canonical test_ids and aliases for the tests on the report
    valid_test_names: set[str] = set()
    for t_name in report_tests:
        tid = r.resolve(t_name)
        if tid:
            valid_test_names.add(tid.lower())
            test_obj = r.get_test(tid)
            if test_obj:
                valid_test_names.add(test_obj.test_name.lower())
                for alias in test_obj.aliases:
                    valid_test_names.add(alias.lower())
        else:
            valid_test_names.add(t_name.lower())

    for valid_name in valid_test_names:
        norm_valid = normalize_alias(valid_name)
        if norm_valid and norm_valid in norm_q:
            return True, "Matched report test name or alias"

    # 4. Check for general educational lab questions (e.g. fasting, range definitions)
    for topic in GENERAL_LAB_TOPICS:
        if topic in norm_q:
            return True, "Matched general lab report educational topic"

    # If neither matched, the question is out of scope
    return False, CANNED_OUT_OF_SCOPE_MESSAGE
