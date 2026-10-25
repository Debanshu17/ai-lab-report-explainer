"""Pure deterministic Knowledge Base template explainer (kb_template mode).

Zero LLM calls. Assembles structured educational explanations directly from curated
Knowledge Base fields and deterministic flagging results. Serves as the gold-standard,
hallucination-free baseline and safety fallback.
"""

from __future__ import annotations

from typing import Optional, Sequence
from src.data.models import KBSource
from src.kb.retriever import UnifiedKBRetriever, FALLBACK_UNAVAILABLE_MESSAGE
from src.explain.schema import TestExplanation, ReportExplanation
from src.explain.hindi import format_hindi_value_meaning, HINDI_FLAG_LABELS, HINDI_UNREVIEWED_NOTICE
from src.safety.disclaimers import (
    get_disclaimer,
    get_urgent_care_footer,
    requires_urgent_care_footer,
)
from src.safety.rules import scan_for_forbidden_terms


class DeterministicTemplateExplainer:
    """Assembles safe, grounded lab explanations directly from curated KB entries."""

    def __init__(self, retriever: Optional[UnifiedKBRetriever] = None):
        self.retriever = retriever or UnifiedKBRetriever()

    def explain_test(
        self,
        test_name: str,
        value: Optional[float],
        unit: str,
        reference_interval: str,
        flag: str,
        language: str = "en",
    ) -> TestExplanation:
        """Deterministically assemble an educational explanation for a single test row."""
        is_hi = language.strip().lower() == "hi"
        flag_upper = flag.strip().upper()

        # Step 1: Retrieve curated KB context
        kb_ctx = self.retriever.retrieve_for_test(test_name, flag=flag_upper)
        is_fallback = kb_ctx.get("is_fallback", False)

        val_display = f"{value}" if value is not None else "Not specified"
        unit_display = unit if unit else ""

        if is_fallback:
            if is_hi:
                what_it_measures = "इस परीक्षण के लिए ज्ञानकोश में कोई सत्यापित शैक्षणिक व्याख्या उपलब्ध नहीं है।"
                value_meaning = (
                    f"परीक्षण '{test_name}' के लिए परिणाम {val_display} {unit_display} और सीमा ({reference_interval}) "
                    f"उपलब्ध है, लेकिन इसकी व्याख्या केवल आपके चिकित्सक द्वारा की जानी चाहिए।"
                )
                when_talk = "इस परिणाम और इसके अर्थ को समझने के लिए अपने डॉक्टर से चर्चा करें।"
                questions = [f"मेरे '{test_name}' परीक्षण परिणाम का क्या अर्थ है?"]
            else:
                what_it_measures = FALLBACK_UNAVAILABLE_MESSAGE
                value_meaning = (
                    f"Your result is {val_display} {unit_display} with printed reference interval ({reference_interval}). "
                    f"A curated educational explanation is not currently available for this test. "
                    f"Please discuss this result directly with your healthcare provider."
                )
                when_talk = "Discuss this test and its result with your healthcare provider."
                questions = [f"What does the '{test_name}' test measure and what does my result mean?"]

            factors: list[str] = []
            sources: list[KBSource] = []
            verif = "unverified"
            needs_verif = True

        else:
            factors = kb_ctx.get("factors", [])
            sources = kb_ctx.get("sources", [])
            needs_verif = kb_ctx.get("needs_verification", True)
            verif = "url_confirmed_content_not_read" if needs_verif else "page_content_read_by_assistant"

            if is_hi:
                hindi_summary = kb_ctx.get("hindi_summary", "")
                test_name_hi = kb_ctx.get("test_name_hindi", test_name)
                what_it_measures = f"{test_name_hi}: {hindi_summary}"
                value_meaning = format_hindi_value_meaning(
                    test_name_hindi=test_name_hi,
                    value=value,
                    unit=unit_display,
                    ref_range=reference_interval,
                    flag=flag_upper,
                    hindi_summary=hindi_summary,
                )
                when_talk = (
                    "यदि आपके कोई लक्षण हैं या परिणाम आपकी अपेक्षा से भिन्न हैं, तो अपने डॉक्टर से परामर्श लें।"
                )
                questions = [
                    f"मेरे {test_name_hi} परिणाम का मेरी वर्तमान स्वास्थ्य स्थिति के लिए क्या अर्थ है?",
                    "क्या मुझे इस परिणाम की पुष्टि के लिए पुन: परीक्षण की आवश्यकता है?",
                    "क्या कोई जीवनशैली या आहार संबंधी कारक इस परिणाम को प्रभावित कर सकते हैं?",
                ]
            else:
                what_it_measures = kb_ctx.get("what_it_measures", "")
                flag_context = kb_ctx.get("flag_context", "")

                if flag_upper == "NORMAL":
                    value_meaning = (
                        f"Your observed result of {val_display} {unit_display} falls within the reference "
                        f"interval ({reference_interval}) printed on this report. In general educational context, "
                        f"a value within the reference interval indicates that the measured parameter was at typical "
                        f"physiological levels for the testing laboratory at the time of collection."
                    )
                elif flag_upper == "LOW":
                    value_meaning = (
                        f"Your observed result of {val_display} {unit_display} is below the reference interval "
                        f"({reference_interval}) printed on this report. Curated educational context: {flag_context} "
                        f"Only a qualified physician can evaluate whether this finding is clinically significant for you."
                    )
                elif flag_upper == "HIGH":
                    value_meaning = (
                        f"Your observed result of {val_display} {unit_display} is above the reference interval "
                        f"({reference_interval}) printed on this report. Curated educational context: {flag_context} "
                        f"Only a qualified physician can evaluate whether this finding is clinically significant for you."
                    )
                else:  # NEEDS_REVIEW
                    value_meaning = (
                        f"Your observed result of {val_display} {unit_display} has a reference interval "
                        f"({reference_interval}) that requires manual review or clinical correlation by your healthcare provider."
                    )

                when_talk = kb_ctx.get("when_to_talk_to_a_doctor", "Discuss any out-of-range results with your physician.")
                raw_qs = kb_ctx.get("questions_for_doctor", [])
                questions = raw_qs[:3] if raw_qs else [f"What does this {test_name} result mean for my overall health?"]

        explanation = TestExplanation(
            test_name=test_name,
            test_id=kb_ctx.get("test_id", "UNKNOWN"),
            observed_value=value,
            unit=unit_display,
            reference_interval=reference_interval,
            flag=flag_upper,
            what_it_measures=what_it_measures,
            what_your_value_means=value_meaning,
            factors_that_can_affect_result=factors,
            when_to_talk_to_doctor=when_talk,
            questions_for_doctor=questions,
            sources=sources,
            source_verification=verif,
            needs_verification=needs_verif,
            is_fallback=is_fallback,
            language="hi" if is_hi else "en",
        )

        # Static safety verification on assembled text
        full_text = f"{explanation.what_it_measures} {explanation.what_your_value_means} {explanation.when_to_talk_to_doctor}"
        violations = scan_for_forbidden_terms(full_text)
        if violations:
            raise ValueError(f"Deterministic template generated forbidden term: {violations}")

        return explanation

    def explain_report(
        self,
        extracted_rows: Sequence[dict],
        language: str = "en",
    ) -> ReportExplanation:
        """Generate a complete educational explanation for an entire report.

        Args:
            extracted_rows: List of dicts with keys: name, value, unit, reference_interval, flag.
            language: 'en' or 'hi'
        """
        is_hi = language.strip().lower() == "hi"
        test_explanations: list[TestExplanation] = []
        flags: list[str] = []

        normal_count = 0
        abnormal_count = 0
        review_count = 0

        for row in extracted_rows:
            flag = row.get("flag", "NORMAL")
            flags.append(flag)
            flag_upper = flag.strip().upper()
            if flag_upper == "NORMAL":
                normal_count += 1
            elif flag_upper in {"LOW", "HIGH"}:
                abnormal_count += 1
            else:
                review_count += 1

            expl = self.explain_test(
                test_name=row.get("name", "Unknown"),
                value=row.get("value"),
                unit=row.get("unit", ""),
                reference_interval=row.get("reference_interval", ""),
                flag=flag,
                language=language,
            )
            test_explanations.append(expl)

        total_tests = len(test_explanations)
        disclaimer = get_disclaimer(language=language)

        if is_hi:
            summary = (
                f"इस रिपोर्ट में कुल {total_tests} परीक्षणों का विश्लेषण किया गया: "
                f"{normal_count} परिणाम मुद्रित संदर्भ सीमा के भीतर हैं, "
                f"{abnormal_count} परिणाम सीमा से बाहर हैं, और "
                f"{review_count} परिणामों के लिए चिकित्सकीय समीक्षा की आवश्यकता है। "
                f"यह सारांश केवल शैक्षणिक मार्गदर्शन के लिए है। {HINDI_UNREVIEWED_NOTICE}"
            )
        else:
            summary = (
                f"Analyzed {total_tests} laboratory tests from your report: "
                f"{normal_count} within printed reference range, "
                f"{abnormal_count} outside printed reference range, and "
                f"{review_count} requiring professional review. "
                f"This report is provided solely for educational reference and must be correlated "
                f"with your complete clinical history by your treating physician."
            )

        urgent_footer = get_urgent_care_footer(language=language) if requires_urgent_care_footer(flags) else None

        return ReportExplanation(
            disclaimer=disclaimer,
            tests=test_explanations,
            summary=summary,
            urgent_care_footer=urgent_footer,
            mode="kb_template",
            language="hi" if is_hi else "en",
        )
