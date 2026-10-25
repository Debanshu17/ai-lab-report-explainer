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


## Phase 3: Deterministic Flagging Engine Benchmarks

| Metric | Target | Result | Status |
|---|---|---|---|
| Flagging Agreement across all 40 Reports (818 Rows) | 100.0% | **100.0%** (818 / 818) | PASS |
| Boundary Value Inclusive Flagging (15 CSV Boundary Rows) | 100.0% NORMAL | **100.0%** (15 / 15) | PASS |
| Single-cell Sex-Specific Range Disambiguation | 100.0% | **100.0%** | PASS |
| `typical_range_info` Non-Access Guard (AST Static Analysis) | 0 accesses | **0 accesses** | PASS |
| Alternate Unit Conversion (IFCC HbA1c, standard multipliers) | 100.0% | **100.0%** | PASS |
| Clinical Implausibility Boundary Rejection (`NEEDS_REVIEW`) | 100.0% | **100.0%** | PASS |

## Phase 4: Knowledge Base Ingestion & Retrieval Benchmarks

### KB Ingestion Statistics
- **Ingested Chunks:** 145 chunks
  - 140 Blood Test chunks (20 tests × 7 sections: `what_it_measures`, `if_below_range`, `if_above_range`, `factors`, `when_to_talk_to_a_doctor`, `questions_for_doctor`, `hindi_summary`)
  - 5 General Educational Topic chunks (`WHY_RANGES_DIFFER`, `OUT_OF_RANGE_MEANING`, `FASTING_BEFORE_TEST`, `URGENT_MEDICAL_CARE`, `PROFESSIONAL_INTERPRETATION`)
- **Storage:** Persistent Chroma DB collection `lab_knowledge_base` at `data/chroma/`
- **Embedding Model:** `BAAI/bge-small-en-v1.5` (cosine similarity metric)

### Retrieval Benchmarks

| Benchmark Metric | Scope | Target | Result | Status |
|---|---|---|---|---|
| **Deterministic Alias Resolution Accuracy** | All canonical IDs + aliases across 20 blood tests (123 variants) | 100.0% | **100.0%** (123 / 123) | PASS |
| **Top-1 Vector Retrieval Accuracy** | 30 free-text patient queries across all panels and topics | ≥ 90.0% | **100.0%** (30 / 30) | PASS |
| **Top-3 Vector Retrieval Accuracy** | 30 free-text patient queries across all panels and topics | ≥ 95.0% | **100.0%** (30 / 30) | PASS |
| **Vector Fallback Gating (< 0.65 threshold)** | Non-medical / out-of-KB free-text queries (5 queries) | 100.0% | **100.0%** (5 / 5) | PASS |
| **Uncurated Report Test Fallback** | Uncurated qualitative urine & non-KB tests (5 tests) | 100.0% | **100.0%** (5 / 5) | PASS |

### Provenance & Grounding Verification
- **Source Metadata Preservation:** 100% of retrieved chunks carry source names, URLs, and source verification flags (`page_content_read_by_assistant`, `url_confirmed_content_not_read`, or unverified).
- **Primary vs Secondary Path Separation:** Primary path uses instantaneous in-memory dictionary lookup by `test_id` (0 embeddings needed); Chroma vector retrieval is used exclusively for free-text search and follow-up Q&A.
