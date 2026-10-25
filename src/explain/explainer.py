"""Grounded LLM Explainer and Dual-Mode Explainer router.

Implements llm_grounded mode:
- Feeds ONLY retrieved Knowledge Base chunks into prompt (zero ungrounded medical facts).
- Zero temperature (temperature=0.0).
- Pydantic JSON-schema structured output.
- Deterministic post-generation safety filter: any output with forbidden diagnostic,
  treatment, dosage, or reassurance terms is rejected and replaced with deterministic kb_template.
"""

from __future__ import annotations

import logging
from typing import Optional, Sequence
from pydantic import BaseModel, Field

from src.config import settings
from src.llm.client import LLMClient
from src.kb.retriever import UnifiedKBRetriever
from src.explain.schema import TestExplanation, ReportExplanation
from src.explain.templates import DeterministicTemplateExplainer
from src.safety.rules import is_safe_explanation
from src.safety.disclaimers import (
    get_disclaimer,
    get_urgent_care_footer,
    requires_urgent_care_footer,
)

logger = logging.getLogger(__name__)


class LLMTestResponse(BaseModel):
    """Pydantic schema for structured LLM explanation output."""

    what_it_measures: str = Field(
        description="Plain-language educational summary of what this test measures based ONLY on provided KB"
    )
    what_your_value_means: str = Field(
        description="Non-diagnostic plain-language explanation of value vs printed range based ONLY on provided KB"
    )
    factors_that_can_affect_result: list[str] = Field(
        description="List of common physiological or non-disease factors from the provided KB"
    )
    when_to_talk_to_doctor: str = Field(
        description="Educational advice on when to speak with a physician"
    )
    questions_for_doctor: list[str] = Field(
        description="Exactly 3 educational questions the patient should ask their doctor"
    )


class LLMGroundedExplainer:
    """Grounded LLM explainer with post-generation safety enforcement and automatic fallback."""

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        retriever: Optional[UnifiedKBRetriever] = None,
        template_explainer: Optional[DeterministicTemplateExplainer] = None,
    ):
        self.llm = llm_client or LLMClient()
        self.retriever = retriever or UnifiedKBRetriever()
        self.template_explainer = template_explainer or DeterministicTemplateExplainer(self.retriever)

    def explain_test(
        self,
        test_name: str,
        value: Optional[float],
        unit: str,
        reference_interval: str,
        flag: str,
        language: str = "en",
    ) -> TestExplanation:
        """Generate a grounded LLM explanation, strictly safety-checked before returning."""
        # Fallback tests immediately use template
        kb_ctx = self.retriever.retrieve_for_test(test_name, flag=flag)
        if kb_ctx.get("is_fallback", False):
            return self.template_explainer.explain_test(
                test_name=test_name,
                value=value,
                unit=unit,
                reference_interval=reference_interval,
                flag=flag,
                language=language,
            )

        # Build grounded prompt containing ONLY retrieved KB fields
        val_str = f"{value}" if value is not None else "Not specified"
        lang_instruction = "Respond entirely in Hindi (हिंदी)." if language.strip().lower() == "hi" else "Respond in English."

        prompt = f"""You are an educational laboratory report explainer.
Explain the following laboratory test result in simple, clear language for a patient.

CORE PRINCIPLES (MANDATORY):
1. Explain ONLY using the provided Knowledge Base facts below. Do NOT add external medical facts.
2. NEVER diagnose a condition or tell the user what disease they "have".
3. NEVER mention medicines, tablets, capsules, prescriptions, doses, or treatments.
4. NEVER say the result is "fine", "normal and healthy", "serious", "critical", or "nothing to worry about".
5. Suggest exactly 3 clear, educational questions to ask a doctor.

{lang_instruction}

TEST DETAILS (FROM USER REPORT):
- Test Name: {test_name}
- Observed Result: {val_str} {unit}
- Printed Reference Range: {reference_interval}
- Flag Determined Against Printed Range: {flag}

CURATED KNOWLEDGE BASE CONTEXT (SINGLE SOURCE OF TRUTH):
- What it measures: {kb_ctx.get('what_it_measures', '')}
- Context for this range/flag: {kb_ctx.get('flag_context', '')}
- Factors that can affect result: {', '.join(kb_ctx.get('factors', []))}
- When to talk to a doctor: {kb_ctx.get('when_to_talk_to_a_doctor', '')}
- Curated questions: {', '.join(kb_ctx.get('questions_for_doctor', []))}
"""

        try:
            llm_output: LLMTestResponse = self.llm.generate_structured(
                prompt=prompt,
                response_schema=LLMTestResponse,
            )

            # Safety scan over all generated text
            combined_text = (
                f"{llm_output.what_it_measures} "
                f"{llm_output.what_your_value_means} "
                f"{llm_output.when_to_talk_to_doctor} "
                f"{' '.join(llm_output.questions_for_doctor)}"
            )
            is_safe, violations = is_safe_explanation(combined_text)

            if not is_safe:
                logger.warning(
                    "LLM generated forbidden terms for test '%s': %s. Reverting to deterministic kb_template.",
                    test_name,
                    violations,
                )
                return self.template_explainer.explain_test(
                    test_name=test_name,
                    value=value,
                    unit=unit,
                    reference_interval=reference_interval,
                    flag=flag,
                    language=language,
                )

            # Construct safe, grounded TestExplanation
            return TestExplanation(
                test_name=test_name,
                test_id=kb_ctx.get("test_id", "UNKNOWN"),
                observed_value=value,
                unit=unit,
                reference_interval=reference_interval,
                flag=flag,
                what_it_measures=llm_output.what_it_measures,
                what_your_value_means=llm_output.what_your_value_means,
                factors_that_can_affect_result=llm_output.factors_that_can_affect_result or kb_ctx.get("factors", []),
                when_to_talk_to_doctor=llm_output.when_to_talk_to_doctor,
                questions_for_doctor=llm_output.questions_for_doctor[:3] or kb_ctx.get("questions_for_doctor", [])[:3],
                sources=kb_ctx.get("sources", []),
                source_verification="url_confirmed_content_not_read" if kb_ctx.get("needs_verification") else "page_content_read_by_assistant",
                needs_verification=kb_ctx.get("needs_verification", True),
                is_fallback=False,
                language=language,
            )

        except Exception as e:
            logger.warning("LLM explanation generation failed for '%s': %s. Reverting to deterministic kb_template.", test_name, e)
            return self.template_explainer.explain_test(
                test_name=test_name,
                value=value,
                unit=unit,
                reference_interval=reference_interval,
                flag=flag,
                language=language,
            )

    def explain_report(
        self,
        extracted_rows: Sequence[dict],
        language: str = "en",
    ) -> ReportExplanation:
        """Generate full report explanation using grounded LLM mode."""
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

        if language.strip().lower() == "hi":
            summary = (
                f"इस रिपोर्ट में कुल {total_tests} परीक्षणों का विश्लेषण किया गया: "
                f"{normal_count} परिणाम मुद्रित संदर्भ सीमा के भीतर हैं, "
                f"{abnormal_count} परिणाम सीमा से बाहर हैं, और "
                f"{review_count} परिणामों के लिए चिकित्सकीय समीक्षा की आवश्यकता है।"
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
            mode="llm_grounded",
            language=language,
        )


class DualModeExplainer:
    """Unified explainer supporting both 'kb_template' and 'llm_grounded' modes."""

    def __init__(
        self,
        retriever: Optional[UnifiedKBRetriever] = None,
        llm_client: Optional[LLMClient] = None,
    ):
        self.retriever = retriever or UnifiedKBRetriever()
        self.template_explainer = DeterministicTemplateExplainer(self.retriever)
        self.llm_explainer = LLMGroundedExplainer(
            llm_client=llm_client,
            retriever=self.retriever,
            template_explainer=self.template_explainer,
        )

    def explain_report(
        self,
        extracted_rows: Sequence[dict],
        mode: Optional[str] = None,
        language: str = "en",
    ) -> ReportExplanation:
        """Route report explanation to selected mode ('kb_template' or 'llm_grounded')."""
        selected_mode = (mode or settings.EXPLANATION_MODE).lower()
        if selected_mode == "kb_template":
            return self.template_explainer.explain_report(extracted_rows, language=language)
        return self.llm_explainer.explain_report(extracted_rows, language=language)
