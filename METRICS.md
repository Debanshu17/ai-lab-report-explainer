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


## Phase 5: Explainer & Safety Layer Benchmarks

### DEV Split Explanation Coverage (12 Reports - 231 Rows)
- **Deterministic Explanations Generated (`kb_template`):** 231 / 231 rows (100.0%)
- **Safety Rule Compliance (Code-Enforced):** 100.0% (0 forbidden terms detected)
- **Source Citation & Provenance Preservation:** 100.0% (231 / 231 rows carry source URLs, names, and verification flags)
- **Question Formulation:** 100.0% (all explained tests provide suggested questions for physician discussion)

### Safety Layer & Scanner Verification

| Benchmark Metric | Evaluated Scope | Target | Result | Status |
|---|---|---|---|---|
| **Adversarial Forbidden Terms Recall** | 33 diagnostic, prescription, dosage, & alarm phrases (En/Hi) | 100.0% | **100.0%** (33 / 33) | PASS |
| **Clean Educational Text Specificity** | Curated KB educational clinical context | 0 false alarms | **0 false alarms** (100% pass) | PASS |
| **Automatic Safety Fallback Triggering** | Simulated LLM diagnostic/medication rule violations | 100.0% fallback | **100.0%** reverted to `kb_template` | PASS |
| **Follow-up Q&A Scope Restriction** | In-scope vs out-of-scope symptom/medication questions (11 queries) | 100.0% | **100.0%** (11 / 11) | PASS |
| **Non-Diagnostic Disclaimer Injection** | Every report explanation (En and Hi) | 100.0% | **100.0%** | PASS |
| **Urgent-Care Emergency Footer Gating** | Triggered only on CRITICAL / extreme deviation | 100.0% | **100.0%** | PASS |


## Phase 6: Hindi Localization Benchmarks

### Terminology & Glossary Verification
- **Glossary Coverage:** 20 / 20 blood tests (100.0%) in `data/glossary/hindi_glossary.json`
- **Category Coverage:** 7 / 7 standard clinical categories mapped to Hindi
- **Flag Label Coverage:** 4 / 4 deterministic flags (`NORMAL`, `LOW`, `HIGH`, `NEEDS_REVIEW`) mapped to Hindi

### Devanagari & Invariance Verification

| Benchmark Metric | Evaluated Scope | Target | Result | Status |
|---|---|---|---|---|
| **KB Test Glossary Coverage** | All 20 curated tests with Devanagari name & transliteration | 100.0% | **100.0%** (20 / 20) | PASS |
| **Western Arabic Number Invariance** | Numeric values preserved as Western digits (no Devanagari numerals) | 100.0% | **100.0%** | PASS |
| **Latin Scientific Unit Invariance** | Scientific units preserved in standard Latin characters (`g/dL`, `mg/dL`) | 100.0% | **100.0%** | PASS |
| **Devanagari Numeral Interception** | Rejection of forbidden Devanagari digits (`०-९`) | 100.0% recall | **100.0%** | PASS |
| **In-App Unreviewed Notice Injection** | Surfacing Open Item #3 notice in all Hindi summaries | 100.0% | **100.0%** | PASS |
| **Side-by-Side Review Packet Completeness** | `docs/hindi_review_packet.md` covers all 20 tests and 5 topics | 100.0% | **100.0%** (588 lines) | PASS |


## Phase 7: Web Application (FastAPI & Streamlit UI) Benchmarks

### API Endpoint Coverage & Validation

| Endpoint | Method | Test Scope | Result | Status |
|---|---|---|---|---|
| `/health` | GET | Operational health check & model configurations | 200 OK | PASS |
| `/tests` | GET | Supported tests catalog (all 20 blood tests & aliases) | 200 OK (20 / 20 tests) | PASS |
| `/explain` | POST | Multipart in-memory PDF upload with DEV split sample | 200 OK (0 PII leaked) | PASS |
| `/explain` | POST | Language localization (Hindi `language="hi"`) | 200 OK (Devanagari verified) | PASS |
| `/explain` | POST | Validation: Empty file upload rejection | 400 Bad Request | PASS |
| `/explain` | POST | Validation: Non-PDF format rejection | 400 Bad Request | PASS |
| `/explain` | POST | Validation: File size limit (> 5 MB) | 413 Content Too Large | PASS |
| `/ask` | POST | In-scope follow-up Q&A grounded in report tests | 200 OK (Grounded with citations) | PASS |
| `/ask` | POST | Out-of-scope symptom/medication rejection | 200 OK (Canned safe response) | PASS |

### Frontend UI Capabilities (`app/streamlit_app.py`)
- **Interactive File Upload & Sample Selector:** In-memory upload + DEV sample reports dropdown.
- **Language & Mode Controls:** English / Hindi toggle; `kb_template` / `llm_grounded` toggle.
- **Color-Coded Status Table & Metrics:** Green (Normal), Amber (Low), Red (High), Blue (Needs Review).
- **Expandable Educational Cards:** Result explanation, what it measures, non-diagnostic factors, doctor discussion checkboxes, and source provenance badges.
- **Developer Inspection Panel:** Raw OCR bounding boxes, extraction confidence scores, and pipeline audit traces.
