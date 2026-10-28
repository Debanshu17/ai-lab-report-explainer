"""Real-world report evaluation benchmark.

Runs strictly in 'rules_only' mode:
- 100% local, offline execution.
- No LLM calls (zero patient data leaves the local machine).
- Compares extraction & deterministic flagging against hand-verified CSV labels.
- Computes field-level accuracy, row-level F1, unparsed rate, and wrong-but-confident rate.
- Results are saved to docs/eval_results/real_world.md as a separate benchmark table.
"""

from __future__ import annotations

import csv
import math
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel

# Enforce offline mode
os.environ["HF_HUB_OFFLINE"] = "1"

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import get_logger
from src.extraction.pipeline import run_extraction_pipeline
from src.flagging.flagger import flag_test_result

logger = get_logger(__name__)

REAL_REPORTS_DIR = PROJECT_ROOT / "data" / "real_reports"
REAL_LABELS_DIR = PROJECT_ROOT / "data" / "real_labels"
RESULTS_MD_PATH = PROJECT_ROOT / "docs" / "eval_results" / "real_world.md"


class RealWorldReportMetrics(BaseModel):
    """Evaluation metrics for a single real-world report."""

    report_id: str
    layout_description: str = "Unknown"
    total_gt_rows: int = 0
    total_extracted_rows: int = 0
    true_positives: int = 0
    name_matches: int = 0
    value_matches: int = 0
    unit_matches: int = 0
    range_matches: int = 0
    flag_agreements: int = 0
    unparsed_rows: int = 0
    wrong_confident_rows: int = 0
    failures: List[Dict[str, str]] = []

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
        return (self.value_matches / self.total_gt_rows * 100.0) if self.total_gt_rows else 0.0

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


def load_label_rows(csv_path: Path) -> List[Dict[str, Any]]:
    """Load hand-made label rows from CSV, ignoring blank template lines."""
    rows = []
    if not csv_path.exists():
        return rows

    with open(csv_path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            t_name = (r.get("test_name") or "").strip()
            if not t_name:
                continue

            raw_val = (r.get("value") or "").strip()
            num_val = None
            try:
                num_val = float(raw_val.replace(",", ""))
            except ValueError:
                pass

            rows.append({
                "test_name": t_name,
                "value_str": raw_val,
                "numeric_value": num_val,
                "unit": (r.get("unit") or "").strip(),
                "printed_range": (r.get("printed_range") or "").strip(),
                "expected_flag": (r.get("expected_flag") or "NORMAL").strip().upper(),
            })
    return rows


def evaluate_single_report(pdf_path: Path, label_path: Path) -> RealWorldReportMetrics:
    """Evaluate one real report against its label CSV in rules_only mode."""
    gt_rows = load_label_rows(label_path)
    metrics = RealWorldReportMetrics(
        report_id=pdf_path.stem,
        total_gt_rows=len(gt_rows),
    )

    if not gt_rows:
        return metrics

    pdf_bytes = pdf_path.read_bytes()
    # Strictly rules_only mode: zero LLM involvement
    ext_res = run_extraction_pipeline(pdf_bytes, mode="rules_only")
    ext_rows = ext_res.rows

    metrics.total_extracted_rows = len(ext_rows)
    metrics.unparsed_rows = sum(1 for r in ext_rows if r.is_unparsed)

    matched_ext_indices = set()

    for gt in gt_rows:
        best_idx = None
        best_ext = None

        for idx, ext_row in enumerate(ext_rows):
            if idx in matched_ext_indices:
                continue

            name_match = (
                (ext_row.canonical_test_id and ext_row.canonical_test_id.lower() == gt["test_name"].lower())
                or (ext_row.raw_test_name.strip().lower() == gt["test_name"].strip().lower())
                or (gt["test_name"].strip().lower() in ext_row.raw_test_name.strip().lower())
            )
            if name_match:
                best_idx = idx
                best_ext = ext_row
                break

        if best_ext is None:
            metrics.failures.append({
                "test": gt["test_name"],
                "issue": "Missing test row (False Negative)",
            })
            continue

        matched_ext_indices.add(best_idx)
        ext_row = best_ext

        if ext_row.is_unparsed:
            metrics.failures.append({
                "test": gt["test_name"],
                "issue": "Row extracted as UNPARSED",
            })
            continue

        metrics.true_positives += 1
        metrics.name_matches += 1

        row_is_wrong = False

        # Value comparison
        val_ok = False
        if gt["numeric_value"] is not None and ext_row.numeric_value is not None:
            val_ok = math.isclose(gt["numeric_value"], ext_row.numeric_value, rel_tol=1e-2, abs_tol=1e-2)
        elif gt["numeric_value"] is None and ext_row.is_qualitative:
            val_ok = gt["value_str"].lower() == ext_row.raw_value_text.lower()

        if val_ok:
            metrics.value_matches += 1
        else:
            row_is_wrong = True
            metrics.failures.append({
                "test": gt["test_name"],
                "issue": f"Value mismatch (Label: {gt['value_str']}, Extracted: {ext_row.numeric_value})",
            })

        # Unit comparison
        if gt["unit"].lower() == ext_row.normalized_unit.strip().lower():
            metrics.unit_matches += 1
        else:
            row_is_wrong = True
            metrics.failures.append({
                "test": gt["test_name"],
                "issue": f"Unit mismatch (Label: '{gt['unit']}', Extracted: '{ext_row.normalized_unit}')",
            })

        # Range comparison
        if gt["printed_range"].strip() == ext_row.normalized_range_text.strip():
            metrics.range_matches += 1
        else:
            row_is_wrong = True
            metrics.failures.append({
                "test": gt["test_name"],
                "issue": f"Range mismatch (Label: '{gt['printed_range']}', Extracted: '{ext_row.normalized_range_text}')",
            })

        # Flag comparison
        flag_out = flag_test_result(
            value=ext_row.numeric_value,
            value_text=ext_row.raw_value_text,
            range_text=ext_row.normalized_range_text,
            patient_sex=ext_res.patient_context.gender,
            test_id=ext_row.canonical_test_id,
            unit=ext_row.normalized_unit,
        )

        if flag_out.flag == gt["expected_flag"]:
            metrics.flag_agreements += 1
        else:
            row_is_wrong = True
            metrics.failures.append({
                "test": gt["test_name"],
                "issue": f"Flag mismatch (Expected: {gt['expected_flag']}, Flagger: {flag_out.flag})",
            })

        if row_is_wrong:
            metrics.wrong_confident_rows += 1

    return metrics


def run_real_world_evaluation() -> Dict[str, Any]:
    """Execute evaluation across all real-world reports in data/real_reports/."""
    REAL_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    REAL_LABELS_DIR.mkdir(parents=True, exist_ok=True)

    pdf_files = sorted(list(REAL_REPORTS_DIR.glob("*.pdf")))
    report_metrics_list: List[RealWorldReportMetrics] = []

    for pdf in pdf_files:
        csv_file = REAL_LABELS_DIR / f"{pdf.stem}.csv"
        m = evaluate_single_report(pdf, csv_file)
        report_metrics_list.append(m)

    total_reports = len(pdf_files)
    labeled_reports = [m for m in report_metrics_list if m.total_gt_rows > 0]

    tot_gt = sum(m.total_gt_rows for m in labeled_reports)
    tot_ext = sum(m.total_extracted_rows for m in labeled_reports)
    tot_tp = sum(m.true_positives for m in labeled_reports)
    tot_name = sum(m.name_matches for m in labeled_reports)
    tot_val = sum(m.value_matches for m in labeled_reports)
    tot_unit = sum(m.unit_matches for m in labeled_reports)
    tot_range = sum(m.range_matches for m in labeled_reports)
    tot_flag = sum(m.flag_agreements for m in labeled_reports)
    tot_unparsed = sum(m.unparsed_rows for m in labeled_reports)
    tot_wrong_conf = sum(m.wrong_confident_rows for m in labeled_reports)

    precision = tot_tp / tot_ext if tot_ext else 0.0
    recall = tot_tp / tot_gt if tot_gt else 0.0
    f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) else 0.0

    summary = {
        "total_reports_found": total_reports,
        "labeled_reports_count": len(labeled_reports),
        "total_gt_rows": tot_gt,
        "total_ext_rows": tot_ext,
        "row_f1": f1,
        "precision": precision,
        "recall": recall,
        "name_accuracy_pct": (tot_name / tot_gt * 100.0) if tot_gt else 0.0,
        "value_accuracy_pct": (tot_val / tot_gt * 100.0) if tot_gt else 0.0,
        "unit_accuracy_pct": (tot_unit / tot_gt * 100.0) if tot_gt else 0.0,
        "range_accuracy_pct": (tot_range / tot_gt * 100.0) if tot_gt else 0.0,
        "flag_accuracy_pct": (tot_flag / tot_gt * 100.0) if tot_gt else 0.0,
        "unparsed_rate_pct": (tot_unparsed / tot_ext * 100.0) if tot_ext else 0.0,
        "wrong_confident_rate_pct": (tot_wrong_conf / tot_ext * 100.0) if tot_ext else 0.0,
        "report_metrics": [m.model_dump() for m in report_metrics_list],
    }

    save_markdown_summary(summary)
    return summary


def save_markdown_summary(summary: Dict[str, Any]) -> None:
    """Format evaluation results into docs/eval_results/real_world.md."""
    RESULTS_MD_PATH.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        "# Real-World Report Evaluation Benchmark",
        "",
        f"**Date:** {time.strftime('%B %d, %Y')}",
        "**Execution Mode:** `rules_only` (100% deterministic local extraction; zero LLM calls; zero data transmission)",
        "**Isolation Notice:** These real-world numbers are evaluated independently and **never** averaged into the synthetic evaluation results.",
        "",
        "---",
        "",
        "## 1. Real-World Dataset & Privacy Protocol",
        "",
        "- **Data Source:** Consented, de-identified real clinical laboratory reports.",
        "- **Confidentiality:** All real reports remain strictly inside `data/real_reports/` which is ignored by `.gitignore`. Real patient reports are **never** committed to version control.",
        "- **Evaluation Sandbox:** Zero API calls or network calls are made during real-world evaluation.",
        f"- **Reports Located:** {summary['total_reports_found']} PDF reports in `data/real_reports/`",
        f"- **Reports with Completed Labels:** {summary['labeled_reports_count']}",
        "",
        "---",
        "",
        "## 2. Aggregate Benchmark Numbers",
        "",
    ]

    if summary["labeled_reports_count"] == 0:
        lines.extend([
            "> [!NOTE]",
            "> No labeled real reports were found in `data/real_labels/` at evaluation time.",
            "> To run this benchmark on your de-identified reports:",
            "> 1. Place your de-identified PDFs in `data/real_reports/`.",
            "> 2. Run `python scripts/make_label_template.py` to generate blank CSV label templates.",
            "> 3. Fill in the ground-truth values in `data/real_labels/<report_id>.csv`.",
            "> 4. Run `python src/evaluation/real_world_eval.py` to compute real-world metrics.",
            "",
            "| Metric | Target | Real-World Result | Counts |",
            "|---|---|---|---|",
            "| **Total Reports Evaluated** | >= 1 | **0** | 0 reports |",
            "| **Total Ground Truth Rows** | - | **0** | 0 rows |",
            "| **Row-Level Precision** | >= 0.95 | **N/A** | 0 / 0 |",
            "| **Row-Level Recall** | >= 0.95 | **N/A** | 0 / 0 |",
            "| **Row-Level F1 Score** | >= 0.95 | **N/A** | - |",
            "| **Field-Level Name Accuracy** | >= 95.0% | **N/A** | 0 / 0 |",
            "| **Field-Level Value Accuracy** | >= 95.0% | **N/A** | 0 / 0 |",
            "| **Field-Level Unit Accuracy** | >= 95.0% | **N/A** | 0 / 0 |",
            "| **Field-Level Range Accuracy** | >= 95.0% | **N/A** | 0 / 0 |",
            "| **Deterministic Flag Agreement** | 100.0% | **N/A** | 0 / 0 |",
            "| **Unparsed Row Rate** | <= 5.0% | **N/A** | 0 / 0 |",
            "| **Wrong-but-Confident Rate** | <= 2.0% | **N/A** | 0 / 0 |",
        ])
    else:
        tot_gt = summary["total_gt_rows"]
        tot_ext = summary["total_ext_rows"]
        tot_tp = int(summary["precision"] * tot_ext) if tot_ext else 0
        tot_unparsed = int(summary["unparsed_rate_pct"] * tot_ext / 100.0) if tot_ext else 0
        tot_wrong_conf = int(summary["wrong_confident_rate_pct"] * tot_ext / 100.0) if tot_ext else 0

        lines.extend([
            "| Metric | Target | Real-World Result | Counts (Correct / Total) |",
            "|---|---|---|---|",
            f"| **Total Reports Evaluated** | >= 1 | **{summary['labeled_reports_count']}** | {summary['labeled_reports_count']} reports |",
            f"| **Total Ground Truth Rows** | - | **{tot_gt}** | {tot_gt} rows |",
            f"| **Row-Level Precision** | >= 0.95 | **{summary['precision']:.4f}** | {tot_tp} / {tot_ext} |",
            f"| **Row-Level Recall** | >= 0.95 | **{summary['recall']:.4f}** | {tot_tp} / {tot_gt} |",
            f"| **Row-Level F1 Score** | >= 0.95 | **{summary['row_f1']:.4f}** | - |",
            f"| **Field-Level Name Accuracy** | >= 95.0% | **{summary['name_accuracy_pct']:.2f}%** | {int(summary['name_accuracy_pct'] * tot_gt / 100.0)} / {tot_gt} |",
            f"| **Field-Level Value Accuracy** | >= 95.0% | **{summary['value_accuracy_pct']:.2f}%** | {int(summary['value_accuracy_pct'] * tot_gt / 100.0)} / {tot_gt} |",
            f"| **Field-Level Unit Accuracy** | >= 95.0% | **{summary['unit_accuracy_pct']:.2f}%** | {int(summary['unit_accuracy_pct'] * tot_gt / 100.0)} / {tot_gt} |",
            f"| **Field-Level Range Accuracy** | >= 95.0% | **{summary['range_accuracy_pct']:.2f}%** | {int(summary['range_accuracy_pct'] * tot_gt / 100.0)} / {tot_gt} |",
            f"| **Deterministic Flag Agreement** | 100.0% | **{summary['flag_accuracy_pct']:.2f}%** | {int(summary['flag_accuracy_pct'] * tot_gt / 100.0)} / {tot_gt} |",
            f"| **Unparsed Row Rate** | <= 5.0% | **{summary['unparsed_rate_pct']:.2f}%** | {tot_unparsed} / {tot_ext} |",
            f"| **Wrong-but-Confident Rate** | <= 2.0% | **{summary['wrong_confident_rate_pct']:.2f}%** | {tot_wrong_conf} / {tot_ext} |",
        ])

    lines.extend([
        "",
        "---",
        "",
        "## 3. Real-World Limitations & Constraints",
        "",
        "1. **Sample Diversity:** Real-world laboratory reports exhibit idiosyncratic formatting (scanned image artifacts, non-standard unit abbreviations, varying column orders).",
        "2. **Small Cohort Size:** Hand-verified real-world labels serve as an external sanity check and validation of generalizability, but cannot cover every proprietary hospital EHR layout.",
        "3. **Zero Data Leakage:** Because real-world reports contain sensitive health information, the real-world benchmark enforces `rules_only` mode exclusively, guaranteeing that zero patient tokens leave the local machine.",
    ])

    RESULTS_MD_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[SAVED] Real-world benchmark report to: {RESULTS_MD_PATH.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    res = run_real_world_evaluation()
    print("=" * 60)
    print("REAL-WORLD EVALUATION COMPLETE")
    print(f"Reports found: {res['total_reports_found']} (Labeled: {res['labeled_reports_count']})")
    print(f"Row F1: {res['row_f1']:.4f}, Total GT Rows: {res['total_gt_rows']}")
    print("=" * 60)
