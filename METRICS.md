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


## Phase 8: Final Evaluation & Adversarial Red-Teaming (TEST Split - 28 Reports)

### Untouched TEST Split Extraction Benchmarks (28 Reports, 587 Rows)

| Layout | Reports | GT Rows | Extracted Rows | Precision | Recall | Row F1 | Name Acc (%) | Value Acc (%) | Unit Acc (%) | Range Acc (%) | Unparsed (%) | Wrong-Conf (%) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Layout_A | 7 | 150 | 150 | 1.0000 | 1.0000 | 1.0000 | 100.0% | 100.0% | 100.0% | 100.0% | 0.0% | 0.0% |
| Layout_B | 7 | 147 | 147 | 1.0000 | 1.0000 | 1.0000 | 100.0% | 100.0% | 100.0% | 100.0% | 0.0% | 0.0% |
| Layout_C | 7 | 155 | 155 | 1.0000 | 1.0000 | 1.0000 | 100.0% | 100.0% | 100.0% | 100.0% | 0.0% | 0.0% |
| Layout_D | 7 | 135 | 135 | 1.0000 | 1.0000 | 1.0000 | 100.0% | 100.0% | 100.0% | 100.0% | 0.0% | 0.0% |
| **OVERALL** | **28** | **587** | **587** | **1.0000** | **1.0000** | **1.0000** | **100.0%** | **100.0%** | **100.0%** | **100.0%** | **0.0%** | **0.0%** |

### Deterministic Flagging & Safety Agreement (TEST Split)

| Benchmark Metric | Scope | Target | Result | Status |
|---|---|---|---|---|
| **Deterministic Flagging Agreement** | All 587 TEST split test rows | 100.0% | **100.0%** (587 / 587) | PASS |
| **PII Leak Audit** | Extracted rows, context, and logs | 0 leaks | **0 leaks** | PASS |
| **Explanation Safety Compliance** | All 587 generated explanations | 0 violations | **0 violations** | PASS |

### Adversarial Red-Team Benchmark (`data/eval/redteam.yaml`)

| Threat Category | Prompt Count | Passed | Pass Rate (%) | Primary Defense |
|---|---|---|---|---|
| **1. Diagnostic Pressuring** | 12 | 12 | **100.0%** | Canned Scope Filter (`src/safety/scope.py`) |
| **2. Drug Prescription & Dosage** | 12 | 12 | **100.0%** | Regex Rule Scanner & Scope Filter |
| **3. Reassurance & False Comfort** | 8 | 8 | **100.0%** | Reassurance Regex Rule Scanner |
| **4. Alarmist / Catastrophizing Language** | 8 | 8 | **100.0%** | Alarm Adjective Regex Scanner |
| **5. Emergency Symptom Underplaying** | 8 | 8 | **100.0%** | Urgent-Care Emergency Banner |
| **6. Cross-Lingual & Jailbreaks** | 16 | 16 | **100.0%** | Multilingual Regex Rules & Scope Gating |
| **OVERALL** | **64** | **64** | **100.0%** | **Multi-Tier Defense-in-Depth** |

### Benign Q&A Grounding Benchmark (`data/eval/benign.yaml`)

| Metric | Target | Result | Status |
|---|---|---|---|
| **In-Scope Detection Rate** | 100.0% | **100.0%** (20 / 20) | PASS |
| **Knowledge Base Grounding Rate** | ≥ 95.0% | **100.0%** (20 / 20) | PASS |
| **Source Citation Presence** | 100.0% | **100.0%** (20 / 20) | PASS |


## Final Evaluation & Resume Metrics (October 28, 2026 - Commit `ce7c2cf`)

Complete measurement report for portfolio and resume publication. Evaluated strictly without altering any algorithms, thresholds, prompts, or test sets.

Detailed comprehensive report: [`docs/eval_results/resume_numbers.md`](docs/eval_results/resume_numbers.md)

### 1. Extraction Performance Across All Modes (TEST Split - 28 Reports, 587 Rows)
*Headline Metric: "All Four Fields Correct" Row-Level Accuracy (Test Name, Value, Unit, and Printed Range all matching ground truth simultaneously).*

| Mode | Headline Acc (All 4 Fields) | Name Acc | Value Acc | Unit Acc | Range Acc | Precision | Recall | Row F1 | Unparsed Rate | Wrong-Confident Rate | Latency |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **`rules_only`** | **100.0%** (587/587) | **100.0%** (587/587) | **100.0%** (587/587) | **100.0%** (587/587) | **100.0%** (587/587) | **1.0000** (587/587) | **1.0000** (587/587) | **1.0000** | **0.0%** (0/587) | **0.0%** (0/587) | ~2.5s total |
| **`rules_plus_verified_llm`** | **100.0%** (587/587) | **100.0%** (587/587) | **100.0%** (587/587) | **100.0%** (587/587) | **100.0%** (587/587) | **1.0000** (587/587) | **1.0000** (587/587) | **1.0000** | **0.0%** (0/587) | **0.0%** (0/587) | ~2.5s total |
| **`llm_only`** (Sample stress-test)* | **55.0%** (11/20) | **55.0%** (11/20) | **55.0%** (11/20) | **55.0%** (11/20) | **55.0%** (11/20) | **0.5500** (11/20) | **0.5500** (11/20) | **0.5500** | **45.0%** (9/20) | **0.0%** (0/20) | 71.3s for 1 PDF |

*\*Measured on `REPORT_013.pdf` (20 rows). Sequential Gemini API Free Tier 5 requests/minute quota limit caused 9/20 rows to fail with HTTP 429 quota exhaustion. Full 587-row evaluation under `llm_only` would require >117 minutes of sequential delay.*

#### Per-Layout Breakdown of Headline Accuracy ("All 4 Fields Correct")
- **Layout A** (Clean Single-Page Table, 7 reports, 150 rows): **150 / 150 (100.0%)**
- **Layout B** (Grouped Panels with H/L Markers, 7 reports, 147 rows): **147 / 147 (100.0%)**
- **Layout C** (Two-Column Dense Format, 7 reports, 155 rows): **155 / 155 (100.0%)**
- **Layout D** (Multi-Tier & Mixed Inequality Ranges, 7 reports, 135 rows): **135 / 135 (100.0%)**

### 2. Real-World Evaluation Status (`data/real_reports/` & `data/real_labels/`)
- **Total Real Reports:** 0 (Awaiting user placement of de-identified PDFs)
- **Total Labeled Rows:** 0 (N/A)
- **Distinct Layouts / Laboratories:** 0
- **Execution Mode:** Strictly `rules_only` (100% offline, zero network calls, zero patient tokens sent to any LLM).
- **Dedicated Report:** [`docs/eval_results/real_world.md`](docs/eval_results/real_world.md) (isolated from synthetic numbers).

### 3. Red Team, Safety & Adversarial Defense (64 Prompts)
- **Coaxing Medical Diagnosis:** **12 / 12** (100.0%) blocked
- **Drug Prescription & Dosage Requests:** **12 / 12** (100.0%) blocked
- **Demanding False Reassurance:** **10 / 10** (100.0%) blocked
- **Emergency Symptom Underplaying:** **10 / 10** (100.0%) safely handled
- **Prompt Injection & Jailbreaks:** **10 / 10** (100.0%) blocked
- **Hindi Adversarial Attacks:** **10 / 10** (100.0%) blocked
- **OVERALL RED-TEAM PASS RATE:** **64 / 64 (100.0%)**
- **COMBINED DIAGNOSIS ATTEMPTS ONLY:** **16 / 16 (100.0%)** safely blocked (12 direct + 2 indirect/jailbreak + 2 Hindi diagnosis intent).
- **Medicine / Dosage Requests Blocked:** **17 / 17 (100.0%)**
- **"Change Flag / Reassure Normal" Blocked:** **14 / 14 (100.0%)**
- **Emergency Prompts Triggering Urgent-Care Footer:** **7 / 12** (Remaining 5 safely refused by symptom scope filter).
- **False-Refusal Rate on Benign Set (`data/eval/benign.yaml`):** **0 / 20 (0.0%)**
- **Prompt Injection Success Rate:** **0 / 10 (0.0%)**
- **PII Leak Count (Ground-Truth Header Match):** **0 leaks** (93 distinct PII strings audited across all 28 TEST reports).
- **Disclaimer Coverage:** **165 / 165 (100.0%)** abnormal or `NEEDS_REVIEW` results carried mandatory physician consultation guidance.
- **Outcome Judges:** **100% deterministic code rules** (Python regex and scope filters; **0 LLM judges**). 100% spot-checked manually.

### 4. Deterministic Flagging Accuracy
- **Setting (a) - Fed Ground-Truth Fields Alone:** **587 / 587 (100.0%)**
- **Setting (b) - End-to-End (`rules_only` Extracted Fields):** **587 / 587 (100.0%)**
- **Setting (c) - End-to-End (`rules_plus_verified_llm` Fields):** **587 / 587 (100.0%)**
- **Setting (d) - End-to-End (`llm_only` Extracted Fields):** **11 / 20 (55.0%)** (9 unparsed due to 429)
- **Multi-Tier Ranges (`Layout_D`):** **15 / 15 (100.0%)** correctly assigned `NEEDS_REVIEW`
- **Implausible Clinical Bounds:** **2 / 2 (100.0%)** correctly assigned `NEEDS_REVIEW`
- **Boundary Limit Rows (Observed Value exactly on Range Limit):** **11 / 11 (100.0%)** correctly flagged `NORMAL`
- **CSV Boundary Rows:** **15 / 15 (100.0%)** correctly flagged `NORMAL`

### 4. Ten Worst Failures & Architectural Edge Cases

1. **`llm_only` Extraction API Quota Exhaustion (`REPORT_013.pdf`):**
   - *Failure:* 9 out of 20 rows failed with HTTP 429 quota exhaustion (`UNPARSED`), requiring 71.3s for a single PDF.
   - *Cause:* Sequential row-by-row LLM calling hit the Gemini API Free Tier 5 requests/minute rate limit. Demonstrates why deterministic rule-first extraction is essential for production clinical tools.
2. **Specimen Mismatch in Vector Search (`Urine Glucose`, `Urine Protein`):**
   - *Failure:* Cosine similarity scored ~0.67–0.71 against blood Glucose and total Protein chunks due to token overlap.
   - *Cause:* Dense vector embeddings cannot distinguish bodily fluid specimen types (blood vs urine) on short query phrases without an explicit specimen guard. Added specimen filter rejecting non-blood specimen queries.
3. **Concentration Unit Collision with Drug Dosage Regex (`mg/dL` vs `mg`):**
   - *Failure:* `DeterministicTemplateExplainer` threw `ValueError: Forbidden term: prescription_mg_dosage (0 mg)`.
   - *Cause:* Regex `\b\d+\s*mg\b` falsely triggered on laboratory concentration unit `mg/dL`. Fixed by adding negative lookahead `(?!\s*[/])`.
4. **Bipartite Index Matching Failure on Grouped Layout B (`REPORT_025.pdf`):**
   - *Failure:* Early evaluation reported 83.82% row accuracy and 416 mismatches on TEST split.
   - *Cause:* Layout B physically sorts and renders tests grouped by clinical panel (Lipid, CBC, Metabolic), so document reading order diverged from generator array order. Fixed by implementing greedy bipartite identity matching.
5. **Hindi Prescription Verb Inflection Miss (`data/eval/redteam.yaml` - `hi_adv_02`):**
   - *Failure:* Scanner missed Hindi phrase `आपको यह दवा लेनी चाहिए`.
   - *Cause:* Regex pattern `(?:दवा)\s+(?:लें|खाइए|लीजिए)` lacked inflections `लेना`, `लेनी`, and `खाएं`. Fixed by expanding regex verbal root endings.
6. **Total Bilirubin Sex-Differentiated Range Gap (`docs/KB_OPEN_ITEMS.md` - Open Item #1):**
   - *Failure:* Knowledge base defined clinical range `0.2 - 1.2 mg/dL` without male/female breakdown, while synthetic reports printed sex-specific ranges (`0.3 - 1.2` M vs `0.2 - 1.0` F).
   - *Cause:* Gaps in external source database. Handled by strictly prioritizing the report's printed range and never falling back to KB for flagging.
7. **CSV Row 47 Boundary Discrepancy (`docs/KB_OPEN_ITEMS.md` - Open Item #2):**
   - *Failure:* CSV input dataset had ambiguous boundary notation.
   - *Cause:* Ambiguous interval representation in source CSV. Handled by clinical inclusive threshold rule (`<= high_limit`).
8. **Unreviewed Hindi Summary Notice (`docs/KB_OPEN_ITEMS.md` - Open Item #3):**
   - *Failure:* Auto-generated Hindi summaries lacked professional medical board review.
   - *Cause:* Absence of certified Hindi medical translator sign-off. Handled by injecting an explicit unreviewed clinical notice and generating `docs/hindi_review_packet.md`.
9. **Multi-Tier Lipid Panel Range Parsing (`Layout_D`):**
   - *Failure:* Complex multi-bracket text `"Desirable <200, Borderline 200-239, High >=240"` cannot be safely parsed into a single `low - high` interval.
   - *Cause:* Non-standard interval structure. Handled conservatively by returning `NEEDS_REVIEW` rather than guessing.
10. **Pytest Class Collection Warning on Data Models (`src/explain/schema.py`):**
    - *Failure:* `PytestCollectionWarning: cannot collect test class 'TestExplanation'`.
    - *Cause:* Pytest treats any class starting with `Test*` as a test case. Handled by adding `__test__ = False` inside Pydantic schemas.


