# Project Evaluation Metrics (METRICS.md)

Evaluation results logged honestly across development. Tuning is conducted strictly on the **DEV** split (12 reports). The **TEST** split (28 reports) is reserved for the final benchmark.

## Phase 2: PDF Extraction Benchmarks (DEV Split - 12 Reports)

### Mode: `rules_only`

| Layout | Reports | GT Rows | Extracted | Row F1 | Name Acc (%) | Value Acc (%) | Unit Acc (%) | Range Acc (%) | Unparsed (%) | Wrong-Conf (%) |
|---|---|---|---|---|---|---|---|---|---|---|
| Layout_A | 3 | 51 | 51 | 1.000 | 100.0% | 100.0% | 100.0% | 100.0% | 0.0% | 0.0% |
| Layout_B | 3 | 64 | 64 | 1.000 | 100.0% | 100.0% | 100.0% | 100.0% | 0.0% | 0.0% |
| Layout_C | 3 | 62 | 62 | 1.000 | 100.0% | 100.0% | 100.0% | 100.0% | 0.0% | 0.0% |
| Layout_D | 3 | 54 | 54 | 1.000 | 100.0% | 100.0% | 100.0% | 100.0% | 0.0% | 0.0% |
| **OVERALL** | **12** | **231** | **231** | **1.000** | **100.0%** | **100.0%** | **100.0%** | **100.0%** | **0.0%** | **0.0%** |

### Mode: `rules_plus_verified_llm`

| Layout | Reports | GT Rows | Extracted | Row F1 | Name Acc (%) | Value Acc (%) | Unit Acc (%) | Range Acc (%) | Unparsed (%) | Wrong-Conf (%) |
|---|---|---|---|---|---|---|---|---|---|---|
| Layout_A | 3 | 51 | 51 | 1.000 | 100.0% | 100.0% | 100.0% | 100.0% | 0.0% | 0.0% |
| Layout_B | 3 | 64 | 64 | 1.000 | 100.0% | 100.0% | 100.0% | 100.0% | 0.0% | 0.0% |
| Layout_C | 3 | 62 | 62 | 1.000 | 100.0% | 100.0% | 100.0% | 100.0% | 0.0% | 0.0% |
| Layout_D | 3 | 54 | 54 | 1.000 | 100.0% | 100.0% | 100.0% | 100.0% | 0.0% | 0.0% |
| **OVERALL** | **12** | **231** | **231** | **1.000** | **100.0%** | **100.0%** | **100.0%** | **100.0%** | **0.0%** | **0.0%** |

### DEV Split Extraction Failure Analysis

- **Zero extraction failures detected on the DEV split across all 12 reports.**
- All 231 lab test rows across Layouts A, B, C, and D were parsed with 100% field-level accuracy and 0 unparsed rows.
