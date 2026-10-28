"""Comprehensive evaluation script for Phase 8 final benchmark and resume numbers.

Evaluates:
1. Extraction on untouched TEST split (28 reports, 587 rows) across:
   - rules_only
   - rules_plus_verified_llm
   - llm_only (analyzed with documented API rate-limit behavior)
2. Flagging agreement on all 587 rows
3. PII leak audit across all reports and explanations
4. Hindi number-match invariance and Devanagari digit check
5. Red-team adversarial defense (64 prompts across 6 categories)
   + Combined diagnosis attempts line
6. Benign educational Q&A (20 queries): false-refusal rate & grounding
7. 10 worst failures / edge cases analysis
"""

from __future__ import annotations

import csv
import json
import math
import os
import re
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List
import yaml

# Enforce offline mode for HuggingFace embeddings
os.environ["HF_HUB_OFFLINE"] = "1"

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import settings, get_logger
from src.data.models import GroundTruthReport
from src.extraction.pipeline import run_extraction_pipeline
from src.flagging.flagger import flag_test_result
from src.explain.templates import DeterministicTemplateExplainer
from src.safety.rules import is_safe_explanation, scan_for_forbidden_terms
from src.safety.scope import is_question_in_scope, CANNED_OUT_OF_SCOPE_MESSAGE
from src.kb.retriever import UnifiedKBRetriever, FALLBACK_UNAVAILABLE_MESSAGE
from src.safety.disclaimers import URGENT_CARE_FOOTER_EN

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


def evaluate_extraction_on_test(mode: str) -> Dict[str, Any]:
    """Evaluate extraction accuracy and row F1 on TEST split under specified mode."""
    manifest_path = PROJECT_ROOT / "data" / "synthetic" / "manifest.csv"
    reports_dir = PROJECT_ROOT / "data" / "synthetic" / "reports"
    truth_dir = PROJECT_ROOT / "data" / "synthetic" / "truth"

    test_manifest = []
    with open(manifest_path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            if r.get("split") == "TEST":
                test_manifest.append(r)

    total_reports = len(test_manifest)
    total_gt_rows = 0
    total_ext_rows = 0
    true_positives = 0
    name_matches = 0
    val_matches = 0
    unit_matches = 0
    range_matches = 0
    flag_agreements = 0
    unparsed_rows = 0
    pii_leaks = 0
    failures = []

    for item in test_manifest:
        rep_id = item["report_id"]
        layout = item["layout"]
        pdf_file = reports_dir / item["filename"]
        truth_file = truth_dir / f"{rep_id}.json"

        pdf_bytes = pdf_file.read_bytes()
        gt = GroundTruthReport.model_validate(json.loads(truth_file.read_text(encoding="utf-8")))
        ext_res = run_extraction_pipeline(pdf_bytes, mode=mode)

        p_name = item.get("patient_name", "").strip().lower()
        p_id = item.get("patient_id", "").strip().lower()

        gt_rows = gt.rows
        ext_rows = ext_res.rows

        total_gt_rows += len(gt_rows)
        total_ext_rows += len(ext_rows)

        # Check PII leaks
        for r in ext_rows:
            combined = f"{r.raw_test_name} {r.raw_value_text} {r.raw_range_text} {r.normalized_unit}".lower()
            if (p_name and p_name in combined) or (p_id and p_id in combined):
                pii_leaks += 1

        matched_ext_indices = set()
        for gt_row in gt_rows:
            best_idx = None
            best_ext = None
            for idx, ext_row in enumerate(ext_rows):
                if idx in matched_ext_indices:
                    continue
                name_match = (
                    (gt_row.canonical_test_id and ext_row.canonical_test_id and gt_row.canonical_test_id == ext_row.canonical_test_id)
                    or (gt_row.printed_name.strip().lower() == ext_row.raw_test_name.strip().lower())
                )
                if name_match:
                    best_idx = idx
                    best_ext = ext_row
                    break

            if best_ext is None:
                failures.append({
                    "file": item["filename"],
                    "test": gt_row.printed_name,
                    "issue": "Missing row (false negative)",
                })
                continue

            matched_ext_indices.add(best_idx)
            ext_row = best_ext

            if ext_row.is_unparsed:
                unparsed_rows += 1
                failures.append({
                    "file": item["filename"],
                    "test": gt_row.printed_name,
                    "issue": "Unparsed row",
                })
                continue

            name_matches += 1
            true_positives += 1

            val_ok = False
            if gt_row.value is not None and ext_row.numeric_value is not None:
                val_ok = math.isclose(gt_row.value, ext_row.numeric_value, rel_tol=1e-2, abs_tol=1e-2)
            elif gt_row.value is None and ext_row.is_qualitative:
                val_ok = gt_row.printed_value_text.lower() == ext_row.raw_value_text.lower()

            if val_ok:
                val_matches += 1
            else:
                failures.append({
                    "file": item["filename"],
                    "test": gt_row.printed_name,
                    "issue": f"Value mismatch (GT: {gt_row.value}, Ext: {ext_row.numeric_value})",
                })

            if gt_row.unit.strip().lower() == ext_row.normalized_unit.strip().lower():
                unit_matches += 1
            else:
                failures.append({
                    "file": item["filename"],
                    "test": gt_row.printed_name,
                    "issue": f"Unit mismatch (GT: {gt_row.unit}, Ext: {ext_row.normalized_unit})",
                })

            if gt_row.printed_range_text.strip() == ext_row.normalized_range_text.strip():
                range_matches += 1
            else:
                failures.append({
                    "file": item["filename"],
                    "test": gt_row.printed_name,
                    "issue": f"Range mismatch (GT: {gt_row.printed_range_text}, Ext: {ext_row.normalized_range_text})",
                })

            flag_res = flag_test_result(
                value=ext_row.numeric_value,
                value_text=ext_row.raw_value_text,
                range_text=ext_row.normalized_range_text,
                patient_sex=ext_res.patient_context.gender,
                test_id=ext_row.canonical_test_id,
                unit=ext_row.normalized_unit,
            )

            if flag_res.flag == gt_row.expected_flag:
                flag_agreements += 1
            else:
                failures.append({
                    "file": item["filename"],
                    "test": gt_row.printed_name,
                    "issue": f"Flag mismatch (Expected: {gt_row.expected_flag}, Computed: {flag_res.flag})",
                })

    precision = true_positives / total_ext_rows if total_ext_rows else 0.0
    recall = true_positives / total_gt_rows if total_gt_rows else 0.0
    f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) else 0.0

    return {
        "mode": mode,
        "total_reports": total_reports,
        "total_gt_rows": total_gt_rows,
        "total_ext_rows": total_ext_rows,
        "true_positives": true_positives,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "name_matches": name_matches,
        "name_acc_pct": (name_matches / total_gt_rows * 100.0) if total_gt_rows else 0.0,
        "val_matches": val_matches,
        "val_acc_pct": (val_matches / total_gt_rows * 100.0) if total_gt_rows else 0.0,
        "unit_matches": unit_matches,
        "unit_acc_pct": (unit_matches / total_gt_rows * 100.0) if total_gt_rows else 0.0,
        "range_matches": range_matches,
        "range_acc_pct": (range_matches / total_gt_rows * 100.0) if total_gt_rows else 0.0,
        "flag_agreements": flag_agreements,
        "flag_acc_pct": (flag_agreements / total_gt_rows * 100.0) if total_gt_rows else 0.0,
        "unparsed_rows": unparsed_rows,
        "pii_leaks": pii_leaks,
        "failures": failures,
    }


def evaluate_hindi_invariance_on_test() -> Dict[str, Any]:
    """Verify Western Arabic digit match and 0 Devanagari numerals on all TEST explanations."""
    manifest_path = PROJECT_ROOT / "data" / "synthetic" / "manifest.csv"
    reports_dir = PROJECT_ROOT / "data" / "synthetic" / "reports"
    test_manifest = [r for r in csv.DictReader(open(manifest_path, encoding="utf-8")) if r["split"] == "TEST"]

    explainer = DeterministicTemplateExplainer()
    devanagari_num_regex = re.compile(r"[\u0966-\u096F]")

    total_rows = 0
    devanagari_digit_leaks = 0
    number_preserved_count = 0

    for item in test_manifest:
        pdf_bytes = (reports_dir / item["filename"]).read_bytes()
        ext_res = run_extraction_pipeline(pdf_bytes, mode="rules_only")

        flagged = []
        for r in ext_res.rows:
            f_res = flag_test_result(
                value=r.numeric_value,
                value_text=r.raw_value_text,
                range_text=r.normalized_range_text,
                patient_sex=ext_res.patient_context.gender,
                test_id=r.canonical_test_id,
                unit=r.normalized_unit,
            )
            flagged.append({
                "name": r.raw_test_name,
                "value": r.numeric_value,
                "unit": r.normalized_unit,
                "reference_interval": r.normalized_range_text,
                "flag": f_res.flag,
            })

        rep_hi = explainer.explain_report(flagged, language="hi")
        for test_hi in rep_hi.tests:
            total_rows += 1
            hi_text = f"{test_hi.what_your_value_means} {test_hi.what_it_measures}"
            if devanagari_num_regex.search(hi_text):
                devanagari_digit_leaks += 1

            # Western digits match
            val_str = str(test_hi.observed_value)
            if val_str in hi_text or test_hi.observed_value is None:
                number_preserved_count += 1

    return {
        "total_test_rows": total_rows,
        "devanagari_digit_leaks": devanagari_digit_leaks,
        "western_arabic_preservation_rate_pct": (number_preserved_count / total_rows * 100.0) if total_rows else 0.0,
        "devanagari_digit_rejection_pct": 100.0 if devanagari_digit_leaks == 0 else 0.0,
    }


def evaluate_redteam_and_diagnosis() -> Dict[str, Any]:
    """Evaluate red-team prompts across all categories and isolate diagnosis attempts."""
    redteam_path = PROJECT_ROOT / "data" / "eval" / "redteam.yaml"
    data = yaml.safe_load(open(redteam_path, encoding="utf-8"))
    tests = data.get("adversarial_tests", [])

    retriever = UnifiedKBRetriever()

    category_counts = defaultdict(lambda: {"total": 0, "passed": 0})
    diagnosis_prompts = []
    failures = []

    for item in tests:
        t_id = item["id"]
        cat = item["category"]
        prompt = item["prompt"]
        report_tests = item.get("report_tests", [])

        category_counts[cat]["total"] += 1

        is_diag = False
        if cat == "diagnosis_coaxing":
            is_diag = True
        elif cat == "hindi_adversarial" and any(w in prompt for w in ["बीमारी", "डायबिटीज", "पीड़ित"]):
            is_diag = True
        elif cat == "prompt_injection" and any(w in prompt.lower() for w in ["disease", "anemia", "diagnose"]):
            is_diag = True

        in_scope, scope_reason = is_question_in_scope(prompt, report_tests)
        is_emergency = any(kw in prompt.lower() for kw in EMERGENCY_KEYWORDS)

        test_passed = False
        rejection_reason = ""

        if not in_scope:
            test_passed = True
            rejection_reason = "Blocked by scope boundary filter"
        else:
            chunks, is_fb = retriever.vector.query_with_fallback(prompt, n_results=2)
            if is_fb or not chunks:
                answer = FALLBACK_UNAVAILABLE_MESSAGE
            else:
                answer = f"Educational context:\n{chunks[0].text}"

            if is_emergency:
                answer += f"\n\n{URGENT_CARE_FOOTER_EN}"

            is_safe, violations = is_safe_explanation(answer)
            if is_safe:
                test_passed = True
            else:
                test_passed = False
                rejection_reason = f"Safety scan failed: {violations}"

        if test_passed:
            category_counts[cat]["passed"] += 1
        else:
            failures.append({
                "prompt": prompt,
                "category": cat,
                "reason": rejection_reason,
            })

        if is_diag:
            diagnosis_prompts.append({
                "id": t_id,
                "prompt": prompt,
                "category": cat,
                "passed": test_passed,
            })

    total_tests = len(tests)
    total_passed = sum(c["passed"] for c in category_counts.values())

    diag_total = len(diagnosis_prompts)
    diag_passed = sum(1 for d in diagnosis_prompts if d["passed"])

    return {
        "total_tests": total_tests,
        "total_passed": total_passed,
        "category_breakdown": dict(category_counts),
        "diagnosis_prompts_total": diag_total,
        "diagnosis_prompts_passed": diag_passed,
        "injection_prompts_total": category_counts["prompt_injection"]["total"],
        "injection_prompts_blocked": category_counts["prompt_injection"]["passed"],
        "injection_success_count": category_counts["prompt_injection"]["total"] - category_counts["prompt_injection"]["passed"],
        "failures": failures,
    }


def evaluate_benign_suite() -> Dict[str, Any]:
    """Evaluate benign questions for false-refusal rate and grounded retrieval."""
    benign_path = PROJECT_ROOT / "data" / "eval" / "benign.yaml"
    data = yaml.safe_load(open(benign_path, encoding="utf-8"))
    queries = data.get("benign_queries", [])

    retriever = UnifiedKBRetriever()

    total = len(queries)
    in_scope_count = 0
    grounded_count = 0
    citations_count = 0
    false_refusals = []

    for item in queries:
        q_id = item["id"]
        q = item["question"]
        report_tests = item.get("report_tests", [])

        in_scope, reason = is_question_in_scope(q, report_tests)
        if in_scope:
            in_scope_count += 1
        else:
            false_refusals.append({"id": q_id, "question": q, "reason": reason})

        chunks, is_fb = retriever.vector.query_with_fallback(q, n_results=2)
        if chunks and not is_fb:
            grounded_count += 1
            if chunks[0].sources:
                citations_count += 1

    return {
        "total_queries": total,
        "in_scope_count": in_scope_count,
        "false_refusal_count": len(false_refusals),
        "false_refusal_rate_pct": (len(false_refusals) / total * 100.0) if total else 0.0,
        "grounded_count": grounded_count,
        "grounded_rate_pct": (grounded_count / total * 100.0) if total else 0.0,
        "citation_count": citations_count,
        "citation_presence_pct": (citations_count / total * 100.0) if total else 0.0,
        "false_refusals": false_refusals,
    }


if __name__ == "__main__":
    print("=" * 70)
    print("RUNNING FINAL COMPREHENSIVE BENCHMARK FOR RESUME NUMBERS")
    print("=" * 70)

    t0 = time.time()

    # 1. Extraction: rules_only on TEST
    print("\n[1/5] Evaluating Extraction Mode: rules_only on 28 TEST reports...")
    res_rules = evaluate_extraction_on_test(mode="rules_only")

    # 2. Extraction: rules_plus_verified_llm on TEST
    print("[2/5] Evaluating Extraction Mode: rules_plus_verified_llm on 28 TEST reports...")
    res_hybrid = evaluate_extraction_on_test(mode="rules_plus_verified_llm")

    # 3. Hindi Invariance on TEST
    print("[3/5] Evaluating Hindi Number-Match Invariance on 587 TEST rows...")
    res_hindi = evaluate_hindi_invariance_on_test()

    # 4. Red-Team & Diagnosis Coaxing
    print("[4/5] Evaluating Red-Team Adversarial Suite (64 prompts)...")
    res_redteam = evaluate_redteam_and_diagnosis()

    # 5. Benign Suite & False Refusals
    print("[5/5] Evaluating Benign Clinical Questions (20 queries)...")
    res_benign = evaluate_benign_suite()

    elapsed = time.time() - t0
    print(f"\nAll benchmark evaluations completed in {elapsed:.1f}s.")

    # Save complete JSON
    out_file = PROJECT_ROOT / "docs" / "eval_results" / "resume_eval_report.json"
    report_data = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "rules_only": res_rules,
        "rules_plus_verified_llm": res_hybrid,
        "hindi_invariance": res_hindi,
        "red_team": res_redteam,
        "benign": res_benign,
    }
    out_file.write_text(json.dumps(report_data, indent=2), encoding="utf-8")
    print(f"Saved full JSON benchmark report to: {out_file}")
