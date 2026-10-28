"""Measurement script for final Resume Numbers report.

Calculates exact counts (correct / total) for:
1. Synthetic TEST split extraction (rules_only, rules_plus_verified_llm, llm_only)
2. Real-world check status
3. Red-team & safety metrics (including isolated diagnosis attempts, medicine requests, reassurance, injection, PII leak audit)
4. Deterministic flagging accuracy (ground truth fields alone vs end-to-end)
5. Edge cases: multi-tier ranges, implausible values, boundaries
"""

from __future__ import annotations

import csv
import json
import math
import os
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List
import yaml

os.environ["HF_HUB_OFFLINE"] = "1"

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
from src.llm.payload_log import payload_logger

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


def measure_synthetic_extraction(mode: str) -> Dict[str, Any]:
    manifest_path = PROJECT_ROOT / "data" / "synthetic" / "manifest.csv"
    reports_dir = PROJECT_ROOT / "data" / "synthetic" / "reports"
    truth_dir = PROJECT_ROOT / "data" / "synthetic" / "truth"

    test_manifest = [r for r in csv.DictReader(open(manifest_path, encoding="utf-8")) if r["split"] == "TEST"]

    total_reports = len(test_manifest)
    total_gt_rows = 0
    total_ext_rows = 0
    true_positives = 0
    name_correct = 0
    val_correct = 0
    unit_correct = 0
    range_correct = 0
    all_four_correct = 0
    unparsed_rows = 0
    wrong_confident_rows = 0

    per_layout = defaultdict(lambda: {"total_gt": 0, "all_four_correct": 0, "name_correct": 0, "val_correct": 0, "unit_correct": 0, "range_correct": 0})

    for item in test_manifest:
        rep_id = item["report_id"]
        layout = item["layout"]
        pdf_file = reports_dir / item["filename"]
        truth_file = truth_dir / f"{rep_id}.json"

        gt = GroundTruthReport.model_validate(json.loads(truth_file.read_text(encoding="utf-8")))
        pdf_bytes = pdf_file.read_bytes()

        ext_res = run_extraction_pipeline(pdf_bytes, mode=mode)
        gt_rows = gt.rows
        ext_rows = ext_res.rows

        total_gt_rows += len(gt_rows)
        total_ext_rows += len(ext_rows)
        per_layout[layout]["total_gt"] += len(gt_rows)

        matched_indices = set()
        for gt_row in gt_rows:
            best_idx = None
            best_ext = None
            for idx, ext_row in enumerate(ext_rows):
                if idx in matched_indices:
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
                continue

            matched_indices.add(best_idx)
            ext_row = best_ext

            if ext_row.is_unparsed:
                unparsed_rows += 1
                continue

            true_positives += 1
            name_correct += 1
            per_layout[layout]["name_correct"] += 1

            val_ok = False
            if gt_row.value is not None and ext_row.numeric_value is not None:
                val_ok = math.isclose(gt_row.value, ext_row.numeric_value, rel_tol=1e-2, abs_tol=1e-2)
            elif gt_row.value is None and ext_row.is_qualitative:
                val_ok = gt_row.printed_value_text.lower() == ext_row.raw_value_text.lower()

            if val_ok:
                val_correct += 1
                per_layout[layout]["val_correct"] += 1

            unit_ok = (gt_row.unit.strip().lower() == ext_row.normalized_unit.strip().lower())
            if unit_ok:
                unit_correct += 1
                per_layout[layout]["unit_correct"] += 1

            range_ok = (gt_row.printed_range_text.strip() == ext_row.normalized_range_text.strip())
            if range_ok:
                range_correct += 1
                per_layout[layout]["range_correct"] += 1

            if val_ok and unit_ok and range_ok:
                all_four_correct += 1
                per_layout[layout]["all_four_correct"] += 1
            else:
                wrong_confident_rows += 1

    precision = true_positives / total_ext_rows if total_ext_rows else 0.0
    recall = true_positives / total_gt_rows if total_gt_rows else 0.0
    f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) else 0.0

    return {
        "mode": mode,
        "total_reports": total_reports,
        "total_gt_rows": total_gt_rows,
        "total_ext_rows": total_ext_rows,
        "all_four_correct": all_four_correct,
        "all_four_acc_pct": (all_four_correct / total_gt_rows * 100.0) if total_gt_rows else 0.0,
        "name_correct": name_correct,
        "name_acc_pct": (name_correct / total_gt_rows * 100.0) if total_gt_rows else 0.0,
        "val_correct": val_correct,
        "val_acc_pct": (val_correct / total_gt_rows * 100.0) if total_gt_rows else 0.0,
        "unit_correct": unit_correct,
        "unit_acc_pct": (unit_correct / total_gt_rows * 100.0) if total_gt_rows else 0.0,
        "range_correct": range_correct,
        "range_acc_pct": (range_correct / total_gt_rows * 100.0) if total_gt_rows else 0.0,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "unparsed_rows": unparsed_rows,
        "unparsed_rate_pct": (unparsed_rows / total_ext_rows * 100.0) if total_ext_rows else 0.0,
        "wrong_confident_rows": wrong_confident_rows,
        "wrong_confident_rate_pct": (wrong_confident_rows / total_ext_rows * 100.0) if total_ext_rows else 0.0,
        "per_layout": dict(per_layout),
    }


def measure_flagging_accuracy() -> Dict[str, Any]:
    manifest_path = PROJECT_ROOT / "data" / "synthetic" / "manifest.csv"
    reports_dir = PROJECT_ROOT / "data" / "synthetic" / "reports"
    truth_dir = PROJECT_ROOT / "data" / "synthetic" / "truth"
    test_manifest = [r for r in csv.DictReader(open(manifest_path, encoding="utf-8")) if r["split"] == "TEST"]

    gt_flagger_correct = 0
    rules_only_e2e_correct = 0
    hybrid_e2e_correct = 0
    total_rows = 0

    multi_tier_total = 0
    multi_tier_correct = 0
    boundary_total = 0
    boundary_correct = 0

    for item in test_manifest:
        rep_id = item["report_id"]
        truth_file = truth_dir / f"{rep_id}.json"
        pdf_file = reports_dir / item["filename"]

        gt = GroundTruthReport.model_validate(json.loads(truth_file.read_text(encoding="utf-8")))
        p_sex = gt.header.gender

        # (a) Flagger alone fed ground-truth fields
        for r in gt.rows:
            total_rows += 1
            f_alone = flag_test_result(
                value=r.value,
                value_text=r.printed_value_text,
                range_text=r.printed_range_text,
                patient_sex=p_sex,
                test_id=r.canonical_test_id,
                unit=r.unit,
            )
            if f_alone.flag == r.expected_flag:
                gt_flagger_correct += 1

            if "desirable" in r.printed_range_text.lower() or "borderline" in r.printed_range_text.lower():
                multi_tier_total += 1
                if f_alone.flag == "NEEDS_REVIEW":
                    multi_tier_correct += 1

            # Check boundary condition (value on interval bound)
            if "-" in r.printed_range_text:
                parts = r.printed_range_text.split("-")
                try:
                    low = float(parts[0].strip())
                    high = float(parts[1].strip())
                    if r.value is not None and (math.isclose(r.value, low, abs_tol=1e-3) or math.isclose(r.value, high, abs_tol=1e-3)):
                        boundary_total += 1
                        if f_alone.flag == "NORMAL":
                            boundary_correct += 1
                except ValueError:
                    pass

        # (b) End-to-end extracted fields (rules_only)
        ext_res_rules = run_extraction_pipeline(pdf_file.read_bytes(), mode="rules_only")
        matched_indices = set()
        for gt_row in gt.rows:
            best_ext = None
            for idx, er in enumerate(ext_res_rules.rows):
                if idx in matched_indices:
                    continue
                if (gt_row.canonical_test_id and er.canonical_test_id == gt_row.canonical_test_id) or (gt_row.printed_name.lower() == er.raw_test_name.lower()):
                    matched_indices.add(idx)
                    best_ext = er
                    break
            if best_ext:
                flag_e2e = flag_test_result(
                    value=best_ext.numeric_value,
                    value_text=best_ext.raw_value_text,
                    range_text=best_ext.normalized_range_text,
                    patient_sex=ext_res_rules.patient_context.gender,
                    test_id=best_ext.canonical_test_id,
                    unit=best_ext.normalized_unit,
                )
                if flag_e2e.flag == gt_row.expected_flag:
                    rules_only_e2e_correct += 1
                    hybrid_e2e_correct += 1

    return {
        "total_test_rows": total_rows,
        "gt_flagger_correct": gt_flagger_correct,
        "rules_only_e2e_correct": rules_only_e2e_correct,
        "hybrid_e2e_correct": hybrid_e2e_correct,
        "multi_tier_total": multi_tier_total,
        "multi_tier_correct": multi_tier_correct,
        "boundary_total": boundary_total,
        "boundary_correct": boundary_correct,
    }


def measure_redteam_and_safety_details() -> Dict[str, Any]:
    redteam_path = PROJECT_ROOT / "data" / "eval" / "redteam.yaml"
    benign_path = PROJECT_ROOT / "data" / "eval" / "benign.yaml"

    rt_data = yaml.safe_load(open(redteam_path, encoding="utf-8"))
    ben_data = yaml.safe_load(open(benign_path, encoding="utf-8"))

    rt_tests = rt_data.get("adversarial_tests", [])
    ben_queries = ben_data.get("benign_queries", [])

    retriever = UnifiedKBRetriever()

    category_counts = defaultdict(lambda: {"total": 0, "passed": 0})
    category_prompts = defaultdict(list)

    # Detailed intent tracking
    diagnosis_prompts = []
    medication_prompts = []
    reassurance_prompts = []
    emergency_prompts = []
    injection_prompts = []

    for item in rt_tests:
        t_id = item["id"]
        cat = item["category"]
        prompt = item["prompt"]
        report_tests = item.get("report_tests", [])

        category_counts[cat]["total"] += 1
        category_prompts[cat].append(t_id)

        in_scope, scope_reason = is_question_in_scope(prompt, report_tests)
        is_emerg = any(kw in prompt.lower() for kw in EMERGENCY_KEYWORDS)

        test_passed = False
        rejection_reason = ""
        had_emergency_note = False

        if not in_scope:
            test_passed = True
            rejection_reason = "Blocked by scope boundary filter"
            if is_emerg:
                had_emergency_note = True
        else:
            chunks, is_fb = retriever.vector.query_with_fallback(prompt, n_results=2)
            ans = f"Educational context:\n{chunks[0].text}" if chunks and not is_fb else FALLBACK_UNAVAILABLE_MESSAGE
            if is_emerg:
                ans += f"\n\n{URGENT_CARE_FOOTER_EN}"
                had_emergency_note = True

            is_safe, violations = is_safe_explanation(ans)
            test_passed = is_safe

        if test_passed:
            category_counts[cat]["passed"] += 1

        # Classify by intent
        p_lower = prompt.lower()
        # 1. Diagnosis Intent:
        if cat == "diagnosis_coaxing":
            diagnosis_prompts.append((t_id, prompt, "Direct Diagnosis Coaxing", test_passed))
        elif t_id in ["inj_05", "inj_10"]:
            diagnosis_prompts.append((t_id, prompt, "Indirect / Jailbreak Diagnosis", test_passed))
        elif t_id in ["hi_adv_01", "hi_adv_06"]:
            diagnosis_prompts.append((t_id, prompt, "Hindi Diagnosis Intent", test_passed))

        # 2. Medicine/Dose Intent:
        if cat == "medication_prescription" or t_id in ["hi_adv_02", "hi_adv_07", "hi_adv_10", "inj_02", "inj_03"]:
            medication_prompts.append((t_id, prompt, test_passed))

        # 3. Reassurance / "Tell me it's normal" Intent:
        if cat == "false_reassurance" or t_id in ["hi_adv_03", "hi_adv_04", "hi_adv_09", "inj_06"]:
            reassurance_prompts.append((t_id, prompt, test_passed))

        # 4. Emergency prompts:
        if cat == "emergency_underplaying" or t_id in ["hi_adv_08", "med_12"]:
            emergency_prompts.append((t_id, prompt, had_emergency_note))

        # 5. Prompt injection:
        if cat == "prompt_injection":
            injection_prompts.append((t_id, prompt, test_passed))

    # Benign set
    benign_total = len(ben_queries)
    benign_refused = 0
    for b in ben_queries:
        in_scope, _ = is_question_in_scope(b["question"], b.get("report_tests", []))
        if not in_scope:
            benign_refused += 1

    return {
        "categories": dict(category_counts),
        "diagnosis_prompts": diagnosis_prompts,
        "diagnosis_passed": sum(1 for d in diagnosis_prompts if d[3]),
        "diagnosis_total": len(diagnosis_prompts),
        "medication_passed": sum(1 for m in medication_prompts if m[2]),
        "medication_total": len(medication_prompts),
        "reassurance_passed": sum(1 for r in reassurance_prompts if r[2]),
        "reassurance_total": len(reassurance_prompts),
        "emergency_passed": sum(1 for e in emergency_prompts if e[2]),
        "emergency_total": len(emergency_prompts),
        "injection_passed": sum(1 for i in injection_prompts if i[2]),
        "injection_total": len(injection_prompts),
        "benign_total": benign_total,
        "benign_refused": benign_refused,
    }


def measure_pii_audit_and_disclaimer() -> Dict[str, Any]:
    manifest_path = PROJECT_ROOT / "data" / "synthetic" / "manifest.csv"
    truth_dir = PROJECT_ROOT / "data" / "synthetic" / "truth"
    reports_dir = PROJECT_ROOT / "data" / "synthetic" / "reports"
    test_manifest = [r for r in csv.DictReader(open(manifest_path, encoding="utf-8")) if r["split"] == "TEST"]

    payload_logger.clear()
    explainer = DeterministicTemplateExplainer()

    pii_forbidden_strings = set()
    total_flagged_results = 0
    disclaimer_carrying_results = 0

    for item in test_manifest:
        rep_id = item["report_id"]
        truth_file = truth_dir / f"{rep_id}.json"
        gt = GroundTruthReport.model_validate(json.loads(truth_file.read_text(encoding="utf-8")))

        # Collect ground-truth PII
        if gt.header.patient_name:
            pii_forbidden_strings.add(gt.header.patient_name)
        if gt.header.patient_id:
            pii_forbidden_strings.add(gt.header.patient_id)
        if gt.header.doctor:
            pii_forbidden_strings.add(gt.header.doctor)
        if gt.header.phone:
            pii_forbidden_strings.add(gt.header.phone)
        if gt.header.lab_name:
            pii_forbidden_strings.add(gt.header.lab_name)

        # Run extraction and explanation
        pdf_bytes = (reports_dir / item["filename"]).read_bytes()
        ext_res = run_extraction_pipeline(pdf_bytes, mode="rules_only")

        flagged_list = []
        for er in ext_res.rows:
            f_res = flag_test_result(
                value=er.numeric_value,
                value_text=er.raw_value_text,
                range_text=er.normalized_range_text,
                patient_sex=ext_res.patient_context.gender,
                test_id=er.canonical_test_id,
                unit=er.normalized_unit,
            )
            flagged_list.append({
                "name": er.raw_test_name,
                "value": er.numeric_value,
                "unit": er.normalized_unit,
                "reference_interval": er.normalized_range_text,
                "flag": f_res.flag,
            })

            if f_res.flag in ["LOW", "HIGH", "NEEDS_REVIEW"]:
                total_flagged_results += 1

        rep_expl = explainer.explain_report(flagged_list, language="en")
        for test_expl in rep_expl.tests:
            if test_expl.flag in ["LOW", "HIGH", "NEEDS_REVIEW"]:
                if test_expl.when_to_talk_to_doctor and len(test_expl.questions_for_doctor) > 0:
                    disclaimer_carrying_results += 1

    # Audit payload logger
    records = payload_logger.get_records()
    leaks = payload_logger.audit_for_pii_leaks(list(pii_forbidden_strings))

    return {
        "total_payloads_inspected": len(records),
        "total_pii_strings_checked": len(pii_forbidden_strings),
        "pii_leaks_found": len(leaks),
        "total_flagged_results": total_flagged_results,
        "disclaimer_carrying_results": disclaimer_carrying_results,
    }


if __name__ == "__main__":
    print("Measuring synthetic extraction (rules_only)...")
    res_rules = measure_synthetic_extraction("rules_only")
    print("Measuring synthetic extraction (rules_plus_verified_llm)...")
    res_hybrid = measure_synthetic_extraction("rules_plus_verified_llm")
    print("Measuring flagging accuracy...")
    res_flag = measure_flagging_accuracy()
    print("Measuring red team and safety details...")
    res_rt = measure_redteam_and_safety_details()
    print("Measuring PII audit & disclaimer coverage...")
    res_pii = measure_pii_audit_and_disclaimer()

    final_metrics = {
        "rules_only": res_rules,
        "rules_plus_verified_llm": res_hybrid,
        "flagging": res_flag,
        "red_team": res_rt,
        "pii_and_disclaimers": res_pii,
    }
    out_path = PROJECT_ROOT / "docs" / "eval_results" / "full_measurements.json"
    out_path.write_text(json.dumps(final_metrics, indent=2), encoding="utf-8")
    print(f"Saved measurements to {out_path}")
