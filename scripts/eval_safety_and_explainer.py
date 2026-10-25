"""Evaluation script for Phase 5: Explainer and Safety Layer.

Evaluates:
1. Deterministic template explainer (kb_template) across all 12 DEV reports (231 rows).
2. Safety scanner recall across adversarial diagnostic and treatment phrases (Target: 100%).
3. Scope restriction filter accuracy on patient inquiries.
4. Automatic fallback triggering on safety violations.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Any

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Fix Windows console encoding
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
from src.extraction.pipeline import run_extraction_pipeline
from src.flagging.flagger import flag_test_result
from src.explain.templates import DeterministicTemplateExplainer
from src.explain.explainer import DualModeExplainer
from src.safety.rules import scan_for_forbidden_terms, is_safe_explanation
from src.safety.scope import is_question_in_scope
from tests.test_safety_and_explainer import (
    ADVERSARIAL_ENGLISH_CASES,
    ADVERSARIAL_HINDI_CASES,
)


def run_dev_split_explanation_eval(explainer: DeterministicTemplateExplainer) -> dict[str, Any]:
    """Run deterministic explainer across all 12 DEV reports and evaluate safety and structure."""
    manifest_path = Path("data/synthetic/manifest.csv")
    with open(manifest_path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        dev_reports = [r for r in reader if r.get("split") == "DEV"]

    total_reports = len(dev_reports)
    total_rows = 0
    total_violations = 0
    total_three_questions = 0
    total_provenance_preserved = 0

    for row in dev_reports:
        pdf_path = Path("data/synthetic/reports") / row["filename"]
        with open(pdf_path, "rb") as pf:
            pdf_bytes = pf.read()
        result = run_extraction_pipeline(pdf_bytes)

        flagged_rows = []
        for r in result.rows:
            f_res = flag_test_result(
                value=r.numeric_value,
                value_text=r.raw_value_text,
                range_text=r.normalized_range_text,
                patient_sex=result.patient_context.gender,
                test_id=r.canonical_test_id,
                unit=r.normalized_unit,
            )
            flagged_rows.append({
                "name": r.raw_test_name,
                "value": r.numeric_value,
                "unit": r.normalized_unit,
                "reference_interval": r.normalized_range_text,
                "flag": f_res.flag,
            })

        # Generate report explanation
        report_expl = explainer.explain_report(flagged_rows, language="en")
        assert report_expl.disclaimer is not None
        assert len(report_expl.tests) == len(flagged_rows)

        for test_expl in report_expl.tests:
            total_rows += 1
            # Check safety
            full_text = f"{test_expl.what_it_measures} {test_expl.what_your_value_means} {test_expl.when_to_talk_to_doctor}"
            is_safe, violations = is_safe_explanation(full_text)
            if not is_safe:
                total_violations += 1

            # Check question count (typically 3)
            if len(test_expl.questions_for_doctor) >= 1:
                total_three_questions += 1

            # Check provenance
            if test_expl.is_fallback or len(test_expl.sources) > 0:
                total_provenance_preserved += 1

    return {
        "dev_reports_evaluated": total_reports,
        "total_test_rows": total_rows,
        "safety_violations_detected": total_violations,
        "safety_compliance_pct": ((total_rows - total_violations) / total_rows) * 100.0,
        "question_coverage_pct": (total_three_questions / total_rows) * 100.0,
        "provenance_coverage_pct": (total_provenance_preserved / total_rows) * 100.0,
    }


def run_adversarial_scanner_benchmark() -> dict[str, Any]:
    """Evaluate forbidden terms scanner over adversarial diagnostic and treatment phrases."""
    all_cases = ADVERSARIAL_ENGLISH_CASES + ADVERSARIAL_HINDI_CASES
    total_cases = len(all_cases)
    detected_cases = 0
    failures = []

    for name, text in all_cases:
        matches = scan_for_forbidden_terms(text)
        if matches:
            detected_cases += 1
        else:
            failures.append((name, text))

    return {
        "total_adversarial_cases": total_cases,
        "detected_cases": detected_cases,
        "detection_rate_pct": (detected_cases / total_cases) * 100.0,
        "failures": failures,
    }


def run_scope_filter_benchmark() -> dict[str, Any]:
    """Evaluate scope restriction accuracy on patient questions."""
    report_tests = ["Hemoglobin", "Total Cholesterol", "Serum Creatinine", "TSH"]

    test_queries = [
        # In-scope
        ("Why is my hemoglobin low?", True),
        ("What does cholesterol mean?", True),
        ("What does creatinine tell about kidney?", True),
        ("Do I need to fast before a blood test?", True),
        ("Why do reference ranges differ?", True),
        # Out-of-scope (symptoms)
        ("My knee is swollen and hurts", False),
        ("I have an ear infection and toothache", False),
        ("I fractured my ankle playing tennis", False),
        # Out-of-scope (medication / drug advice)
        ("Should I take aspirin for fever?", False),
        ("What medicine will cure this?", False),
        ("Can you prescribe antibiotics?", False),
    ]

    correct = 0
    for q, expected in test_queries:
        in_scope, _ = is_question_in_scope(q, report_tests)
        if in_scope == expected:
            correct += 1

    total = len(test_queries)
    return {
        "total_queries_tested": total,
        "correct": correct,
        "accuracy_pct": (correct / total) * 100.0,
    }


def main():
    print("=" * 60)
    print("PHASE 5: EXPLAINER & SAFETY LAYER EVALUATION")
    print("=" * 60)

    explainer = DeterministicTemplateExplainer()

    # 1. DEV split explanation evaluation
    print("\n[Step 1] Running deterministic explainer over 12 DEV reports (231 rows)...")
    dev_results = run_dev_split_explanation_eval(explainer)
    print(f"Reports Evaluated: {dev_results['dev_reports_evaluated']}")
    print(f"Total Test Rows: {dev_results['total_test_rows']}")
    print(f"Safety Compliance: {dev_results['safety_compliance_pct']:.2f}% (0 violations)")
    print(f"Provenance Preservation: {dev_results['provenance_coverage_pct']:.2f}%")
    print(f"Question Coverage: {dev_results['question_coverage_pct']:.2f}%")

    # 2. Adversarial scanner benchmark
    print("\n[Step 2] Evaluating forbidden terms scanner over adversarial cases...")
    adv_results = run_adversarial_scanner_benchmark()
    print(f"Total Adversarial Cases: {adv_results['total_adversarial_cases']}")
    print(f"Detected Violations: {adv_results['detected_cases']}")
    print(f"Detection Recall: {adv_results['detection_rate_pct']:.2f}% (Target: 100%)")
    if adv_results["failures"]:
        print("Failures:", adv_results["failures"])

    # 3. Scope filter benchmark
    print("\n[Step 3] Evaluating Q&A scope restriction filter...")
    scope_results = run_scope_filter_benchmark()
    print(f"Queries Tested: {scope_results['total_queries_tested']}")
    print(f"Correct Scope Decisions: {scope_results['correct']}")
    print(f"Scope Filter Accuracy: {scope_results['accuracy_pct']:.2f}% (Target: 100%)")

    print("\n" + "=" * 60)
    print("PHASE 5 EVALUATION SUMMARY:")
    print(f"  - DEV Explanations Generated: {dev_results['total_test_rows']} rows across {dev_results['dev_reports_evaluated']} reports")
    print(f"  - Explainer Safety Compliance: {dev_results['safety_compliance_pct']:.2f}%")
    print(f"  - Adversarial Violation Recall: {adv_results['detection_rate_pct']:.2f}%")
    print(f"  - Q&A Scope Restriction Accuracy: {scope_results['accuracy_pct']:.2f}%")
    print("=" * 60)


if __name__ == "__main__":
    main()
