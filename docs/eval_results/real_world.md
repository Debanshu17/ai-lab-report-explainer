# Real-World Report Evaluation Benchmark

**Date:** October 28, 2026
**Execution Mode:** `rules_only` (100% deterministic local extraction; zero LLM calls; zero data transmission)
**Isolation Notice:** These real-world numbers are evaluated independently and **never** averaged into the synthetic evaluation results.

---

## 1. Real-World Dataset & Privacy Protocol

- **Data Source:** Consented, de-identified real clinical laboratory reports.
- **Confidentiality:** All real reports remain strictly inside `data/real_reports/` which is ignored by `.gitignore`. Real patient reports are **never** committed to version control.
- **Evaluation Sandbox:** Zero API calls or network calls are made during real-world evaluation.
- **Reports Located:** 0 PDF reports in `data/real_reports/`
- **Reports with Completed Labels:** 0

---

## 2. Aggregate Benchmark Numbers

> [!NOTE]
> No labeled real reports were found in `data/real_labels/` at evaluation time.
> To run this benchmark on your de-identified reports:
> 1. Place your de-identified PDFs in `data/real_reports/`.
> 2. Run `python scripts/make_label_template.py` to generate blank CSV label templates.
> 3. Fill in the ground-truth values in `data/real_labels/<report_id>.csv`.
> 4. Run `python src/evaluation/real_world_eval.py` to compute real-world metrics.

| Metric | Target | Real-World Result | Counts |
|---|---|---|---|
| **Total Reports Evaluated** | >= 1 | **0** | 0 reports |
| **Total Ground Truth Rows** | - | **0** | 0 rows |
| **Row-Level Precision** | >= 0.95 | **N/A** | 0 / 0 |
| **Row-Level Recall** | >= 0.95 | **N/A** | 0 / 0 |
| **Row-Level F1 Score** | >= 0.95 | **N/A** | - |
| **Field-Level Name Accuracy** | >= 95.0% | **N/A** | 0 / 0 |
| **Field-Level Value Accuracy** | >= 95.0% | **N/A** | 0 / 0 |
| **Field-Level Unit Accuracy** | >= 95.0% | **N/A** | 0 / 0 |
| **Field-Level Range Accuracy** | >= 95.0% | **N/A** | 0 / 0 |
| **Deterministic Flag Agreement** | 100.0% | **N/A** | 0 / 0 |
| **Unparsed Row Rate** | <= 5.0% | **N/A** | 0 / 0 |
| **Wrong-but-Confident Rate** | <= 2.0% | **N/A** | 0 / 0 |

---

## 3. Real-World Limitations & Constraints

1. **Sample Diversity:** Real-world laboratory reports exhibit idiosyncratic formatting (scanned image artifacts, non-standard unit abbreviations, varying column orders).
2. **Small Cohort Size:** Hand-verified real-world labels serve as an external sanity check and validation of generalizability, but cannot cover every proprietary hospital EHR layout.
3. **Zero Data Leakage:** Because real-world reports contain sensitive health information, the real-world benchmark enforces `rules_only` mode exclusively, guaranteeing that zero patient tokens leave the local machine.
