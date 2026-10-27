"""AI Lab Report Explainer - Streamlit Web Application.

Educational laboratory report explainer and physician discussion guide.
Features:
- In-memory PDF upload and DEV synthetic sample report selection.
- Language toggle (English / Hindi).
- Mode toggle (Deterministic kb_template vs Grounded llm_grounded).
- Strict non-diagnostic educational disclaimers.
- Interactive color-coded lab test summary table.
- Detailed expandable cards with source provenance and verified badges.
- Patient discussion questions with selection checkboxes.
- Scope-restricted follow-up Q&A chat.
- Developer panel displaying extraction coordinates and pipeline trace.
"""

from __future__ import annotations

import csv
import io
import sys
from pathlib import Path
from typing import Optional

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st

from src.config import settings
from src.extraction.pipeline import run_extraction_pipeline
from src.flagging.flagger import flag_test_result
from src.explain.explainer import DualModeExplainer
from src.explain.templates import DeterministicTemplateExplainer
from src.explain.hindi import HINDI_UNREVIEWED_NOTICE
from src.kb.retriever import UnifiedKBRetriever, FALLBACK_UNAVAILABLE_MESSAGE
from src.safety.scope import is_question_in_scope, CANNED_OUT_OF_SCOPE_MESSAGE
from src.safety.rules import is_safe_explanation
from src.safety.disclaimers import requires_urgent_care_footer, get_urgent_care_footer
from src.llm.client import LLMClient

# Page configuration
st.set_page_config(
    page_title="AI Lab Report Explainer",
    page_icon="🩸",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_resource
def get_retriever():
    return UnifiedKBRetriever()


@st.cache_resource
def get_explainer():
    return DualModeExplainer(retriever=get_retriever())


@st.cache_data
def load_dev_sample_manifest():
    manifest_path = PROJECT_ROOT / "data" / "synthetic" / "manifest.csv"
    if not manifest_path.exists():
        return []
    with open(manifest_path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return [row for row in reader if row.get("split") == "DEV"]


def render_flag_badge(flag: str) -> str:
    flag_upper = flag.strip().upper()
    if flag_upper == "NORMAL":
        return '<span style="background-color: #e6f4ea; color: #137333; padding: 4px 10px; border-radius: 12px; font-weight: 600; font-size: 0.85em;">NORMAL</span>'
    elif flag_upper == "LOW":
        return '<span style="background-color: #fef7e0; color: #b06000; padding: 4px 10px; border-radius: 12px; font-weight: 600; font-size: 0.85em;">LOW</span>'
    elif flag_upper == "HIGH":
        return '<span style="background-color: #fce8e6; color: #c5221f; padding: 4px 10px; border-radius: 12px; font-weight: 600; font-size: 0.85em;">HIGH</span>'
    else:
        return '<span style="background-color: #e8f0fe; color: #1a73e8; padding: 4px 10px; border-radius: 12px; font-weight: 600; font-size: 0.85em;">NEEDS REVIEW</span>'


def main():
    retriever = get_retriever()
    explainer = get_explainer()

    # --- SIDEBAR: Configuration & Sample Selection ---
    st.sidebar.title("⚙️ Settings")

    # Language toggle
    lang_choice = st.sidebar.radio("🌐 Language / भाषा", options=["English (en)", "हिंदी (hi)"], index=0)
    language = "hi" if "हिंदी" in lang_choice else "en"

    # Explanation mode toggle
    mode_choice = st.sidebar.radio(
        "🧠 Explanation Mode",
        options=[
            "kb_template (Deterministic, 0 Cost)",
            "llm_grounded (Grounded LLM)",
        ],
        index=0,
        help="kb_template uses pure deterministic assembly from verified medical KB. llm_grounded passes KB facts through LLM with strict safety scanning.",
    )
    explanation_mode = "kb_template" if "kb_template" in mode_choice else "llm_grounded"

    # Developer inspection toggle
    dev_mode = st.sidebar.checkbox("🛠️ Developer Mode", value=False, help="Inspect raw extracted OCR coordinates, bounding boxes, and pipeline trace.")

    st.sidebar.markdown("---")
    st.sidebar.subheader("📄 Sample Reports (DEV Split)")
    dev_samples = load_dev_sample_manifest()
    sample_options = ["None (Upload Own File)"] + [
        f"{r['report_id']} ({r['layout']} - {r['num_tests']} tests)" for r in dev_samples
    ]
    selected_sample = st.sidebar.selectbox("Choose sample PDF:", options=sample_options)

    # --- MAIN VIEW HEADER ---
    st.title("🩸 AI Lab Report Explainer")
    st.markdown(
        "*Plain-language educational explanations for your blood test reports. "
        "Flags results strictly against the range printed on your report and helps you prepare informed questions for your doctor.*"
    )

    # Educational Disclaimer Banner
    st.warning(
        "⚠️ **EDUCATIONAL TOOL ONLY — NOT MEDICAL ADVICE**\n\n"
        "This tool is strictly an educational resource. It does **NOT** provide medical diagnoses, clinical interpretations, "
        "or treatment recommendations. Reference intervals vary across laboratories. Always discuss your test results directly "
        "with a qualified physician."
    )

    if language == "hi":
        st.info(f"ℹ️ {HINDI_UNREVIEWED_NOTICE}")

    # File input handling
    pdf_bytes: Optional[bytes] = None
    source_label = ""

    if selected_sample != "None (Upload Own File)":
        sample_id = selected_sample.split()[0]
        sample_row = next((r for r in dev_samples if r["report_id"] == sample_id), None)
        if sample_row:
            sample_path = PROJECT_ROOT / "data" / "synthetic" / "reports" / sample_row["filename"]
            if sample_path.exists():
                with open(sample_path, "rb") as sf:
                    pdf_bytes = sf.read()
                source_label = f"Sample Report: {sample_row['filename']} ({sample_row['layout']})"
                st.success(f"Loaded **{source_label}**")

    if pdf_bytes is None:
        uploaded_file = st.file_uploader(
            "Upload Laboratory Report (PDF format, max 5 MB):",
            type=["pdf"],
            help="Files are processed entirely in memory. Patient headers are stripped before processing and no uploads are persisted to disk.",
        )
        if uploaded_file is not None:
            pdf_bytes = uploaded_file.read()
            source_label = uploaded_file.name

    if pdf_bytes is None:
        st.info("👆 Please upload a blood test report PDF or select a DEV sample report from the sidebar.")
        return

    # In-memory processing
    with st.spinner("Analyzing laboratory report..."):
        try:
            # 1. Extraction Pipeline (in-memory)
            extraction_result = run_extraction_pipeline(pdf_bytes)
        except Exception as e:
            st.error(f"Error executing extraction pipeline: {e}")
            return

        if not extraction_result.validation.is_valid:
            st.error(f"Validation Error: {extraction_result.validation.error_message}")
            return

        # 2. Flag test rows deterministically
        flagged_rows = []
        flags_list = []
        for r in extraction_result.rows:
            f_res = flag_test_result(
                value=r.numeric_value,
                value_text=r.raw_value_text,
                range_text=r.normalized_range_text,
                patient_sex=extraction_result.patient_context.gender,
                test_id=r.canonical_test_id,
                unit=r.normalized_unit,
            )
            flagged_rows.append({
                "name": r.raw_test_name,
                "value": r.numeric_value,
                "unit": r.normalized_unit,
                "reference_interval": r.normalized_range_text,
                "flag": f_res.flag,
            })
            flags_list.append(f_res.flag)

        # 3. Generate Report Explanation
        report_explanation = explainer.explain_report(
            extracted_rows=flagged_rows,
            mode=explanation_mode,
            language=language,
        )

    # --- URGENT CARE ALERT (if triggered) ---
    if requires_urgent_care_footer(flags_list):
        st.error(f"🚨 **{get_urgent_care_footer(language=language)}**")

    # --- SUMMARY METRICS ---
    st.markdown("### 📊 Overview")
    normal_count = sum(1 for f in flags_list if f == "NORMAL")
    abnormal_count = sum(1 for f in flags_list if f in {"LOW", "HIGH"})
    review_count = sum(1 for f in flags_list if f not in {"NORMAL", "LOW", "HIGH"})

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Tests Extracted", len(flagged_rows))
    m2.metric("Within Printed Range", normal_count)
    m3.metric("Outside Printed Range", abnormal_count)
    m4.metric("Needs Review", review_count)

    st.markdown(f"*{report_explanation.summary}*")
    st.markdown("---")

    # --- RESULTS TABLE ---
    st.markdown("### 📋 Test Summary")
    table_rows = []
    for test in report_explanation.tests:
        val_display = f"{test.observed_value}" if test.observed_value is not None else "N/A"
        badge_html = render_flag_badge(test.flag)
        table_rows.append(f"<tr>"
                          f"<td><b>{test.test_name}</b></td>"
                          f"<td>{val_display}</td>"
                          f"<td>{test.unit}</td>"
                          f"<td><code>{test.reference_interval}</code></td>"
                          f"<td>{badge_html}</td>"
                          f"</tr>")

    table_html = f"""
    <table style="width: 100%; border-collapse: collapse; margin-bottom: 25px;">
      <thead>
        <tr style="border-bottom: 2px solid #ddd; text-align: left; background-color: #f8f9fa;">
          <th style="padding: 10px;">Test Name</th>
          <th style="padding: 10px;">Observed Result</th>
          <th style="padding: 10px;">Unit</th>
          <th style="padding: 10px;">Printed Reference Range</th>
          <th style="padding: 10px;">Evaluation Flag</th>
        </tr>
      </thead>
      <tbody>
        {''.join(table_rows)}
      </tbody>
    </table>
    """
    st.markdown(table_html, unsafe_allow_html=True)

    # --- DETAILED EDUCATIONAL CARDS ---
    st.markdown("### 🔍 Detailed Educational Explanations")
    for idx, test in enumerate(report_explanation.tests, 1):
        flag_icon = "🟢" if test.flag == "NORMAL" else ("🟡" if test.flag == "LOW" else ("🔴" if test.flag == "HIGH" else "🔵"))
        val_str = f"{test.observed_value} {test.unit}" if test.observed_value is not None else "Not specified"

        with st.expander(f"{flag_icon} **{test.test_name}**: {val_str} ({test.flag})"):
            c1, c2 = st.columns([2, 1])

            with c1:
                st.markdown(f"**What your result indicates in educational context:**")
                st.write(test.what_your_value_means)

                st.markdown(f"**What this test measures:**")
                st.write(test.what_it_measures)

                if test.factors_that_can_affect_result:
                    st.markdown("**Common physiological / non-disease factors:**")
                    for factor in test.factors_that_can_affect_result:
                        st.markdown(f"- {factor}")

                st.markdown("**When to talk to your doctor:**")
                st.write(test.when_to_talk_to_doctor)

            with c2:
                st.markdown("#### 🩺 Questions for Your Doctor")
                st.caption("Check questions you want to discuss during your appointment:")
                for q_idx, question in enumerate(test.questions_for_doctor):
                    st.checkbox(question, key=f"q_{idx}_{q_idx}")

                st.markdown("#### 📚 Source Citations")
                if test.is_fallback:
                    st.caption("No curated knowledge base entry exists for this specific test.")
                elif test.sources:
                    for src in test.sources:
                        st.markdown(f"- [{src.source_name}]({src.url})")
                    if test.needs_verification:
                        st.info("ℹ️ *Source URL confirmed; clinical content pending final review.*")
                else:
                    st.caption("Curated clinical references.")

    st.markdown("---")

    # --- FOLLOW-UP Q&A CHAT ---
    st.markdown("### 💬 Ask a Follow-up Question")
    st.caption("Ask questions about the tests on your report, reference intervals, or preparing for your doctor visit.")

    report_test_names = [t.test_name for t in report_explanation.tests]

    user_question = st.text_input("Your question:", placeholder="e.g. Why is my creatinine level elevated?")
    if st.button("Ask Assistant"):
        if user_question.strip():
            with st.spinner("Checking question scope and consulting verified knowledge base..."):
                # Scope check
                in_scope, reason = is_question_in_scope(user_question, report_test_names)
                if not in_scope:
                    st.warning(f"⚠️ {CANNED_OUT_OF_SCOPE_MESSAGE}")
                else:
                    chunks, is_fb = retriever.vector.query_with_fallback(user_question, n_results=2)
                    if is_fb or not chunks:
                        st.info(FALLBACK_UNAVAILABLE_MESSAGE)
                    else:
                        top_chunk = chunks[0]
                        answer_text = (
                            f"**Educational context from verified medical reference ({top_chunk.test_name} - {top_chunk.section}):**\n\n"
                            f"{top_chunk.text}\n\n"
                            f"*Always consult your physician for individualized clinical interpretation.*"
                        )
                        st.markdown(answer_text)
                        if top_chunk.sources:
                            st.caption(f"Source: [{top_chunk.sources[0].source_name}]({top_chunk.sources[0].url})")

    # --- DEVELOPER INSPECTION PANEL ---
    if dev_mode:
        st.markdown("---")
        st.subheader("🛠️ Developer Inspection Panel")
        st.markdown("#### Patient Context (Stripped for Privacy)")
        st.json(extraction_result.patient_context.model_dump())

        st.markdown("#### Raw Extracted Rows & Coordinates")
        for i, row in enumerate(extraction_result.rows):
            st.code(
                f"Row {i+1}: Name='{row.raw_test_name}' | Value='{row.raw_value_text}' -> {row.numeric_value} | "
                f"Unit='{row.raw_unit}' -> '{row.normalized_unit}' | Range='{row.raw_range_text}' -> '{row.normalized_range_text}' | "
                f"Page={row.page} | Section={row.section} | Confidence={row.confidence}",
                language="text",
            )


if __name__ == "__main__":
    main()
