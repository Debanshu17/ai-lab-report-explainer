# Knowledge Base Open Items Checklist

These are known gaps in the curated knowledge base (`data/inputs/ai_lab_report_knowledge_base_final.json`).
Per project safety and integrity rules, these items must be resolved by human review, never automated or silently modified by the AI.

---

## 1. Unverified Source URLs (26 of 35 Entries)
- [ ] **Status: PENDING HUMAN REVIEW**
- **Description:** 26 source entries in `ai_lab_report_knowledge_base_final.json` currently have verification status `"url_confirmed_content_not_read"`. Only 9 sources have been content-verified (`page_content_read_by_assistant`).
- **Required Action:** A human reviewer must open each of the 26 URLs, compare the page text against the KB entry fields (`clinical_summary`, `general_context_low`, `general_context_high`, `factors_that_can_affect_result`), confirm accuracy, and update `verification` to `page_content_read_by_human` (or equivalent) and set `needs_verification: false` per entry.
- **Rule:** Do not change any `needs_verification` flag in the KB automatically.

---

## 2. Missing Source for General Topic: URGENT_MEDICAL_CARE
- [ ] **Status: PENDING SOURCE CITATION**
- **Description:** The general topic `URGENT_MEDICAL_CARE` currently contains safety guidance on emergency symptoms (chest pain, shortness of breath, sudden confusion, severe bleeding) but has an empty `sources` array.
- **Required Action:** Before publishing/deployment, a verified source appropriate for the user's country/region (e.g., official NHS / CDC / AIIMS / emergency health authority page) must be cited in `sources` with full provenance.

---

## 3. Unreviewed Hindi Medical Summaries
- [ ] **Status: PENDING NATIVE SPEAKER REVIEW**
- **Description:** All Hindi summaries (`hindi_summary`) and Hindi test names across all 20 blood tests currently have `hindi_reviewed: false`.
- **Required Action:** A native Hindi speaker with healthcare literacy must review the translations to verify clinical nuance, cultural appropriateness, and readability.
- **Rule:** The in-app UI must display the disclosure note: *"Hindi text has not yet been reviewed by a native speaker."* until this item is resolved by a human reviewer.

---

*Last updated: Phase 0 Scaffold*
