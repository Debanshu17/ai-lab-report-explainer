"""Single-run evaluation on the untouched TEST split (28 reports).

Enforces Core Principle #7:
- Honest evaluation: tuned only on DEV; run TEST split once at the end.
- Report failures and weak spots honestly.
- Never inflate or cherry-pick metrics.
"""

from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List
from pydantic import BaseModel

from src.config import settings, get_logger
from src.data.models import GroundTruthReport
from src.extraction.pipeline import run_extraction_pipeline
from src.flagging.flagger import flag_test_result
from src.explain.templates import DeterministicTemplateExplainer
from src.safety.rules import is_safe_explanation

logger = get_logger(__name__)


class SplitMetrics(BaseModel):
    """Aggregate metrics container for evaluation splits."""

    total_reports: int = 0
    total_gt_rows: int = 0
    total_extracted_rows: int = 0
    true_positives: int = 0
    name_matches: int = 0
    val_matches: int = 0
    unit_matches: int = 0
    range_matches: int = 0
    flag_agreements: int = 0
    unparsed_rows: int = 0
    wrong_confident_rows: int = 0
    safety_violations: int = 0
    provenance_preserved: int = 0

    @property
    def precision(self) -> float:
        return self.true_positives / self.total_extracted_rows if self.total_extracted_rows else 0.0

    @property
    def recall(self) -> float:
        return self.true_positives / self.total_gt_rows if self.total_gt_rows else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return (2 * p * r) / (p + r) if (p + r) else 0.0

    @property
    def name_accuracy(self) -> float:
        return (self.name_matches / self.total_gt_rows * 100.0) if self.total_gt_rows else 0.0

    @property
    def value_accuracy(self) -> float:
        return (self.val_matches / self.total_gt_rows * 100.0) if self.total_gt_rows else 0.0

    @property
    def unit_accuracy(self) -> float:
        return (self.unit_matches / self.total_gt_rows * 100.0) if self.total_gt_rows else 0.0

    @property
    def range_accuracy(self) -> float:
        return (self.range_matches / self.total_gt_rows * 100.0) if self.total_gt_rows else 0.0

    @property
    def flag_accuracy(self) -> float:
        return (self.flag_agreements / self.total_gt_rows * 100.0) if self.total_gt_rows else 0.0

    @property
    def unparsed_rate(self) -> float:
        return (self.unparsed_rows / self.total_extracted_rows * 100.0) if self.total_extracted_rows else 0.0

    @property
    def wrong_confident_rate(self) -> float:
        return (self.wrong_confident_rows / self.total_extracted_rows * 100.0) if self.total_extracted_rows else 0.0


def evaluate_test_split(
    manifest_path: Path = Path("data/synthetic/manifest.csv"),
    reports_dir: Path = Path("data/synthetic/reports"),
    truth_dir: Path = Path("data/synthetic/truth"),
) -> Dict[str, Any]:
    """Execute evaluation on all 28 TEST split reports."""
    test_manifest: List[dict] = []
    with open(manifest_path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            if r.get("split") == "TEST":
                test_manifest.append(r)

    overall = SplitMetrics()
    by_layout: Dict[str, SplitMetrics] = defaultdict(SplitMetrics)
    failures: List[dict] = []
    pii_leak_count = 0
    explainer = DeterministicTemplateExplainer()

    for item in test_manifest:
        rep_id = item["report_id"]
        layout = item["layout"]
        pdf_file = reports_dir / item["filename"]
        truth_file = truth_dir / f"{rep_id}.json"

        with open(pdf_file, "rb") as pf:
            pdf_bytes = pf.read()

        gt = GroundTruthReport.model_validate(json.loads(truth_file.read_text(encoding="utf-8")))
        ext_res = run_extraction_pipeline(pdf_bytes)

        # Privacy Audit: check for patient name or patient ID in extracted rows
        p_name = item.get("patient_name", "").strip().lower()
        p_id = item.get("patient_id", "").strip().lower()
        for r in ext_res.rows:
            combined_row_text = f"{r.raw_test_name} {r.raw_value_text} {r.raw_range_text} {r.normalized_unit}".lower()
            if (p_name and p_name in combined_row_text) or (p_id and p_id in combined_row_text):
                pii_leak_count += 1

        gt_rows = gt.rows
        ext_rows = ext_res.rows

        m_all = overall
        m_lay = by_layout[layout]

        m_all.total_reports += 1
        m_lay.total_reports += 1
        m_all.total_gt_rows += len(gt_rows)
        m_all.total_extracted_rows += len(ext_rows)
        m_lay.total_gt_rows += len(gt_rows)
        m_lay.total_extracted_rows += len(ext_rows)

        flagged_for_explainer = []
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
                    "report_id": rep_id,
                    "layout": layout,
                    "test": gt_row.printed_name,
                    "issue": "Missing extracted row (false negative)",
                })
                continue

            matched_ext_indices.add(best_idx)
            ext_row = best_ext

            if ext_row.is_unparsed:
                m_all.unparsed_rows += 1
                m_lay.unparsed_rows += 1
                failures.append({
                    "report_id": rep_id,
                    "layout": layout,
                    "test": gt_row.printed_name,
                    "issue": "Unparsed row",
                })
                continue

            # 1. Name match
            m_all.name_matches += 1
            m_lay.name_matches += 1
            m_all.true_positives += 1
            m_lay.true_positives += 1

            # 2. Value match
            val_ok = False
            if gt_row.value is not None and ext_row.numeric_value is not None:
                val_ok = math.isclose(gt_row.value, ext_row.numeric_value, rel_tol=1e-2, abs_tol=1e-2)
            elif gt_row.value is None and ext_row.is_qualitative:
                val_ok = gt_row.printed_value_text.lower() == ext_row.raw_value_text.lower()

            if val_ok:
                m_all.val_matches += 1
                m_lay.val_matches += 1
            else:
                failures.append({
                    "report_id": rep_id,
                    "layout": layout,
                    "test": gt_row.printed_name,
                    "issue": f"Value mismatch (GT: {gt_row.value}, Ext: {ext_row.numeric_value})",
                })

            # 3. Unit match
            unit_ok = (gt_row.unit.strip().lower() == ext_row.normalized_unit.strip().lower())
            if unit_ok:
                m_all.unit_matches += 1
                m_lay.unit_matches += 1
            else:
                failures.append({
                    "report_id": rep_id,
                    "layout": layout,
                    "test": gt_row.printed_name,
                    "issue": f"Unit mismatch (GT: '{gt_row.unit}', Ext: '{ext_row.normalized_unit}')",
                })

            # 4. Range match
            range_ok = (gt_row.printed_range_text.strip() == ext_row.normalized_range_text.strip())
            if range_ok:
                m_all.range_matches += 1
                m_lay.range_matches += 1
            else:
                failures.append({
                    "report_id": rep_id,
                    "layout": layout,
                    "test": gt_row.printed_name,
                    "issue": f"Range mismatch (GT: '{gt_row.printed_range_text}', Ext: '{ext_row.normalized_range_text}')",
                })

            # 5. Flagging Agreement
            flag_res = flag_test_result(
                value=ext_row.numeric_value,
                value_text=ext_row.raw_value_text,
                range_text=ext_row.normalized_range_text,
                patient_sex=ext_res.patient_context.gender,
                test_id=ext_row.canonical_test_id,
                unit=ext_row.normalized_unit,
            )

            if flag_res.flag == gt_row.expected_flag:
                m_all.flag_agreements += 1
                m_lay.flag_agreements += 1
            else:
                failures.append({
                    "report_id": rep_id,
                    "layout": layout,
                    "test": gt_row.printed_name,
                    "issue": f"Flag mismatch (Expected: {gt_row.expected_flag}, Computed: {flag_res.flag})",
                })

            flagged_for_explainer.append({
                "name": ext_row.raw_test_name,
                "value": ext_row.numeric_value,
                "unit": ext_row.normalized_unit,
                "reference_interval": ext_row.normalized_range_text,
                "flag": flag_res.flag,
            })

        # Check for spurious unmatched extracted rows
        for idx, ext_row in enumerate(ext_rows):
            if idx not in matched_ext_indices:
                failures.append({
                    "report_id": rep_id,
                    "layout": layout,
                    "test": ext_row.raw_test_name,
                    "issue": "Spurious extracted row (false positive)",
                })

        # Run report explanation
        report_expl = explainer.explain_report(flagged_for_explainer, language="en")
        for test_expl in report_expl.tests:
            full_text = f"{test_expl.what_it_measures} {test_expl.what_your_value_means} {test_expl.when_to_talk_to_doctor}"
            is_safe, violations = is_safe_explanation(full_text)
            if not is_safe:
                m_all.safety_violations += 1
            if test_expl.is_fallback or len(test_expl.sources) > 0:
                m_all.provenance_preserved += 1

    return {
        "overall": overall,
        "by_layout": dict(by_layout),
        "failures": failures,
        "pii_leaks": pii_leak_count,
    }


if __name__ == "__main__":
    results = evaluate_test_split()
    ov = results["overall"]
    print("=" * 60)
    print("TEST SPLIT (28 REPORTS) BENCHMARK RESULTS")
    print("=" * 60)
    print(f"Reports Evaluated: {ov.total_reports}")
    print(f"Total Ground Truth Rows: {ov.total_gt_rows}")
    print(f"Total Extracted Rows: {ov.total_extracted_rows}")
    print(f"Row Precision: {ov.precision:.4f}, Recall: {ov.recall:.4f}, F1: {ov.f1:.4f}")
    print(f"Test Name Accuracy: {ov.name_accuracy:.2f}%")
    print(f"Observed Value Accuracy: {ov.value_accuracy:.2f}%")
    print(f"Unit Accuracy: {ov.unit_accuracy:.2f}%")
    print(f"Reference Range Accuracy: {ov.range_accuracy:.2f}%")
    print(f"Flagging Agreement: {ov.flag_accuracy:.2f}%")
    print(f"PII Leaks: {results['pii_leaks']}")
    print(f"Safety Violations in Explanations: {ov.safety_violations}")
    print("=" * 60)
