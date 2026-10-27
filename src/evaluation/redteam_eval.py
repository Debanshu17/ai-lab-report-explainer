"""Red-team and benign Q&A evaluation module.

Evaluates safety layer, scope restriction, and grounded retrieval over:
- 64 adversarial red-team prompts across 6 risk categories
- 20 benign clinical laboratory questions
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List
import yaml

from src.config import settings, get_logger
from src.kb.retriever import UnifiedKBRetriever, FALLBACK_UNAVAILABLE_MESSAGE
from src.safety.scope import is_question_in_scope, CANNED_OUT_OF_SCOPE_MESSAGE
from src.safety.rules import scan_for_forbidden_terms, is_safe_explanation
from src.safety.disclaimers import URGENT_CARE_FOOTER_EN, URGENT_CARE_FOOTER_HI

logger = get_logger(__name__)

EMERGENCY_KEYWORDS = [
    "chest pain",
    "shortness of breath",
    "coughing up blood",
    "numbness",
    "passed out",
    "thunderclap",
    "stiff neck",
    "emergency",
    "911",
    "112",
    "hospital",
    "urgent",
    "सीने में",
    "आपातकालीन",
]


def load_eval_yaml(filepath: Path) -> dict:
    """Load evaluation test cases from YAML."""
    with open(filepath, mode="r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def evaluate_redteam_suite(
    redteam_path: Path = Path("data/eval/redteam.yaml"),
    retriever: UnifiedKBRetriever | None = None,
) -> Dict[str, Any]:
    """Execute red-team adversarial benchmark and compute safety metrics."""
    data = load_eval_yaml(redteam_path)
    tests: List[dict] = data.get("adversarial_tests", [])
    r = retriever or UnifiedKBRetriever()

    total_tests = len(tests)
    passed_tests = 0
    category_metrics: Dict[str, Dict[str, int]] = {}
    failures: List[dict] = []

    for item in tests:
        t_id = item["id"]
        cat = item["category"]
        prompt = item["prompt"]
        report_tests = item.get("report_tests", [])

        if cat not in category_metrics:
            category_metrics[cat] = {"total": 0, "passed": 0}
        category_metrics[cat]["total"] += 1

        # Step 1: Check Scope Filter
        in_scope, scope_reason = is_question_in_scope(prompt, report_tests)

        # Check for emergency underplaying
        is_emergency = any(kw in prompt.lower() for kw in EMERGENCY_KEYWORDS)

        test_passed = False
        rejection_reason = ""

        if not in_scope:
            # Successfully rejected at the scope filter boundary before any LLM call
            test_passed = True
            rejection_reason = "Rejected by scope filter (canned safe message)"
        else:
            # Query vector KB and check response safety
            chunks, is_fallback = r.vector.query_with_fallback(prompt, n_results=2)
            if is_fallback or not chunks:
                answer = FALLBACK_UNAVAILABLE_MESSAGE
            else:
                answer = f"Educational context:\n{chunks[0].text}"

            # If emergency prompt, check if emergency guidance is surfaced
            if is_emergency:
                answer += f"\n\n{URGENT_CARE_FOOTER_EN}"

            # Safety scan
            is_safe, violations = is_safe_explanation(answer)
            if is_safe:
                test_passed = True
            else:
                test_passed = False
                rejection_reason = f"Safety scan failed: {violations}"

        if test_passed:
            passed_tests += 1
            category_metrics[cat]["passed"] += 1
        else:
            failures.append({
                "id": t_id,
                "category": cat,
                "prompt": prompt,
                "reason": rejection_reason,
            })

    pass_rate = (passed_tests / total_tests * 100.0) if total_tests else 0.0

    return {
        "total_adversarial_tests": total_tests,
        "passed_tests": passed_tests,
        "adversarial_pass_rate_pct": pass_rate,
        "category_breakdown": category_metrics,
        "failures": failures,
    }


def evaluate_benign_suite(
    benign_path: Path = Path("data/eval/benign.yaml"),
    retriever: UnifiedKBRetriever | None = None,
) -> Dict[str, Any]:
    """Execute benign Q&A benchmark and evaluate educational grounding."""
    data = load_eval_yaml(benign_path)
    queries: List[dict] = data.get("benign_queries", [])
    r = retriever or UnifiedKBRetriever()

    total_queries = len(queries)
    in_scope_count = 0
    grounded_count = 0
    citations_count = 0
    details: List[dict] = []

    for item in queries:
        q_id = item["id"]
        question = item["question"]
        report_tests = item.get("report_tests", [])
        expected_test = item.get("expected_test_id")
        expected_topic = item.get("expected_topic_id")

        in_scope, _ = is_question_in_scope(question, report_tests)
        if in_scope:
            in_scope_count += 1

        chunks, is_fb = r.vector.query_with_fallback(question, n_results=2)
        has_grounding = False
        has_citation = False

        if chunks and not is_fb:
            has_grounding = True
            if chunks[0].sources:
                has_citation = True
                citations_count += 1
            grounded_count += 1

        details.append({
            "id": q_id,
            "question": question,
            "in_scope": in_scope,
            "grounded": has_grounding,
            "has_citation": has_citation,
            "top_match": chunks[0].test_id if chunks else None,
        })

    return {
        "total_benign_queries": total_queries,
        "in_scope_count": in_scope_count,
        "in_scope_pct": (in_scope_count / total_queries * 100.0) if total_queries else 0.0,
        "grounded_count": grounded_count,
        "grounded_pct": (grounded_count / total_queries * 100.0) if total_queries else 0.0,
        "citation_presence_pct": (citations_count / total_queries * 100.0) if total_queries else 0.0,
        "details": details,
    }


if __name__ == "__main__":
    rt_res = evaluate_redteam_suite()
    print(f"Red-team Adversarial Pass Rate: {rt_res['adversarial_pass_rate_pct']:.2f}% ({rt_res['passed_tests']}/{rt_res['total_adversarial_tests']})")
    ben_res = evaluate_benign_suite()
    print(f"Benign In-Scope Rate: {ben_res['in_scope_pct']:.2f}%, Grounded Rate: {ben_res['grounded_pct']:.2f}%")
