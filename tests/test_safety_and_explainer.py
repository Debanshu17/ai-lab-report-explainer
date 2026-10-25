"""Tests for Safety Layer and Explainer (Phase 5).

Covers:
- 100% detection of forbidden diagnostic, prescription, dosage, and alarm terms in English & Hindi.
- Clean educational text passes with 0 false positives.
- Non-diagnostic educational disclaimer and urgent-care footer injections.
- Scope restriction for patient Q&A (rejecting unrelated symptoms & drug inquiries).
- Deterministic template explainer (kb_template) validation.
- Graceful fallback for uncurated tests (e.g. Urine Glucose).
- Automatic reversion from llm_grounded to kb_template upon simulated safety violation.
"""

from unittest.mock import MagicMock
import pytest

from src.safety.rules import (
    scan_for_forbidden_terms,
    is_safe_explanation,
    FORBIDDEN_ENGLISH_PATTERNS,
    FORBIDDEN_HINDI_PATTERNS,
)
from src.safety.disclaimers import (
    get_disclaimer,
    get_urgent_care_footer,
    requires_urgent_care_footer,
    EDUCATIONAL_DISCLAIMER_EN,
    EDUCATIONAL_DISCLAIMER_HI,
)
from src.safety.scope import is_question_in_scope, CANNED_OUT_OF_SCOPE_MESSAGE
from src.explain.schema import TestExplanation, ReportExplanation
from src.explain.templates import DeterministicTemplateExplainer
from src.explain.explainer import LLMGroundedExplainer, DualModeExplainer, LLMTestResponse
from src.kb.retriever import FALLBACK_UNAVAILABLE_MESSAGE


# Sample adversarial test strings designed to coax forbidden behaviors
ADVERSARIAL_ENGLISH_CASES = [
    ("Diagnosis: you have", "Based on this result, you have chronic kidney disease."),
    ("Diagnosis: diagnosed with", "You are diagnosed with type 2 diabetes."),
    ("Diagnosis: suffer from", "You suffer from severe microcytic anemia."),
    ("Diagnosis: you are suffering", "You are suffering from acute liver failure."),
    ("Prescription: take meds", "You should take medication immediately."),
    ("Prescription: take aspirin", "Please take this supplement twice a day."),
    ("Prescription: prescribed", "The doctor prescribed 10mg atorvastatin."),
    ("Prescription: dosage mg", "Recommended dosage is 500 mg daily."),
    ("Prescription: tablet", "Take two tablets in the morning."),
    ("Prescription: capsule", "One capsule should be taken with meals."),
    ("Prescription: pill", "Take this pill every night."),
    ("Prescription: cure", "This will cure your condition within a week."),
    ("Prescription: treat", "We need to treat this immediately with drugs."),
    ("Reassurance: fine", "Your high cholesterol is completely fine."),
    ("Reassurance: normal and healthy", "Your results are normal and healthy, do not worry."),
    ("Reassurance: nothing to worry about", "There is nothing to worry about here."),
    ("Reassurance: don't worry", "Don't worry about this elevated liver enzyme."),
    ("Alarm: serious", "This low platelet count is very serious."),
    ("Alarm: critical", "You are in critical condition."),
    ("Alarm: danger", "This is an extreme danger to your life."),
    ("Alarm: life-threatening", "This result indicates a life-threatening problem."),
]

ADVERSARIAL_HINDI_CASES = [
    ("Hi Diagnosis: आपको बीमारी है", "परीक्षण के अनुसार आपको बीमारी है।"),
    ("Hi Diagnosis: निदान किया गया", "आपका निदान किया गया है।"),
    ("Hi Diagnosis: आप पीड़ित हैं", "आप गंभीर एनीमिया से पीड़ित हैं।"),
    ("Hi Prescription: दवा लें", "आपको यह दवा लेनी चाहिए।"),
    ("Hi Prescription: गोली", "रोजाना एक गोली खाएं।"),
    ("Hi Prescription: खुराक", "इसकी खुराक 100 मिलीग्राम है।"),
    ("Hi Prescription: इलाज", "इसका तुरंत इलाज करवाएं।"),
    ("Hi Reassurance: चिंता की कोई बात नहीं", "इस परिणाम में चिंता की कोई बात नहीं है।"),
    ("Hi Reassurance: चिंता मत करो", "चिंता मत करो सब सामान्य है।"),
    ("Hi Reassurance: सब ठीक है", "आपके परीक्षण में सब ठीक है।"),
    ("Hi Alarm: खतरा", "यह आपके स्वास्थ्य के लिए बड़ा खतरा है।"),
    ("Hi Alarm: गंभीर", "यह एक गंभीर स्थिति है।"),
]


@pytest.mark.parametrize("rule_name, adversarial_text", ADVERSARIAL_ENGLISH_CASES)
def test_forbidden_words_scanner_catches_english_violations(rule_name, adversarial_text):
    """Verify 100% recall on injected English forbidden terms."""
    matches = scan_for_forbidden_terms(adversarial_text)
    assert len(matches) > 0, f"Failed to catch forbidden pattern '{rule_name}' in: {adversarial_text}"
    is_safe, violations = is_safe_explanation(adversarial_text)
    assert is_safe is False
    assert len(violations) > 0


@pytest.mark.parametrize("rule_name, adversarial_text", ADVERSARIAL_HINDI_CASES)
def test_forbidden_words_scanner_catches_hindi_violations(rule_name, adversarial_text):
    """Verify 100% recall on injected Hindi forbidden terms."""
    matches = scan_for_forbidden_terms(adversarial_text)
    assert len(matches) > 0, f"Failed to catch Hindi pattern '{rule_name}' in: {adversarial_text}"
    is_safe, violations = is_safe_explanation(adversarial_text)
    assert is_safe is False
    assert len(violations) > 0


def test_clean_educational_text_passes_scanner():
    """Verify that purely educational clinical context passes without false positives."""
    clean_text = (
        "Hemoglobin is an iron-rich protein in red blood cells that transports oxygen from lungs "
        "to body tissues. Values below the printed reference interval can be associated with "
        "decreased red cell production, blood loss, or nutritional deficiencies. "
        "Discuss this finding with your physician to evaluate potential underlying factors."
    )
    is_safe, violations = is_safe_explanation(clean_text)
    assert is_safe is True
    assert len(violations) == 0


def test_educational_disclaimers():
    """Verify code-injected disclaimer text in English and Hindi."""
    en_disc = get_disclaimer("en")
    assert "educational tool and does NOT provide medical advice" in en_disc

    hi_disc = get_disclaimer("hi")
    assert "शैक्षणिक साधन है" in hi_disc


def test_urgent_care_footer_rules():
    """Verify urgent care footer triggers only when critical bounds/flags are present."""
    # Normal and out-of-range non-critical flags do NOT trigger footer
    assert requires_urgent_care_footer(["NORMAL", "HIGH", "LOW"]) is False

    # CRITICAL flag triggers footer
    assert requires_urgent_care_footer(["NORMAL", "CRITICAL", "LOW"]) is True

    # Extreme boundary flag triggers footer
    assert requires_urgent_care_footer(["NORMAL"], has_critical_bounds=True) is True

    footer_en = get_urgent_care_footer("en")
    assert "EMERGENCY MEDICAL NOTICE" in footer_en
    assert "911 or 112" in footer_en


def test_scope_checker_in_scope():
    """Verify in-scope questions pass."""
    report_tests = ["Hemoglobin", "Total Cholesterol", "Serum Creatinine"]

    # Mentioning test by name or alias
    in_scope, _ = is_question_in_scope("Why is my hemoglobin low?", report_tests)
    assert in_scope is True

    in_scope, _ = is_question_in_scope("What does serum creatinine indicate?", report_tests)
    assert in_scope is True

    # General lab topics
    in_scope, _ = is_question_in_scope("Do I need to fast before a blood test?", report_tests)
    assert in_scope is True

    in_scope, _ = is_question_in_scope("Why do reference ranges differ between labs?", report_tests)
    assert in_scope is True


def test_scope_checker_out_of_scope_rejection():
    """Verify out-of-scope symptom and drug inquiries are immediately rejected."""
    report_tests = ["Hemoglobin", "TSH"]

    # Unrelated anatomical symptoms
    in_scope, msg = is_question_in_scope("My knee hurts after playing soccer, what should I do?", report_tests)
    assert in_scope is False
    assert msg == CANNED_OUT_OF_SCOPE_MESSAGE

    in_scope, msg = is_question_in_scope("I have a severe cough and sore throat", report_tests)
    assert in_scope is False
    assert msg == CANNED_OUT_OF_SCOPE_MESSAGE

    # Seeking medication / prescription
    in_scope, msg = is_question_in_scope("Should I take aspirin for my headache?", report_tests)
    assert in_scope is False
    assert msg == CANNED_OUT_OF_SCOPE_MESSAGE

    in_scope, msg = is_question_in_scope("What medicine should I take for this?", report_tests)
    assert in_scope is False
    assert msg == CANNED_OUT_OF_SCOPE_MESSAGE


def test_deterministic_template_explainer():
    """Verify deterministic template assembly generates compliant, safe explanations."""
    explainer = DeterministicTemplateExplainer()
    sample_rows = [
        {"name": "Hemoglobin", "value": 11.2, "unit": "g/dL", "reference_interval": "13.0 - 17.0", "flag": "LOW"},
        {"name": "Total Cholesterol", "value": 185.0, "unit": "mg/dL", "reference_interval": "< 200", "flag": "NORMAL"},
        {"name": "Urine Glucose", "value": None, "unit": "", "reference_interval": "Negative", "flag": "NORMAL"},
    ]

    report_expl = explainer.explain_report(sample_rows, language="en")
    assert report_expl.mode == "kb_template"
    assert len(report_expl.tests) == 3
    assert "educational tool" in report_expl.disclaimer.lower()

    # Check Hemoglobin (curated LOW)
    hb_expl = report_expl.tests[0]
    assert hb_expl.test_id == "HEMOGLOBIN"
    assert hb_expl.flag == "LOW"
    assert len(hb_expl.questions_for_doctor) == 3
    assert len(hb_expl.sources) > 0
    assert hb_expl.is_fallback is False

    # Check Urine Glucose (uncurated fallback)
    urine_expl = report_expl.tests[2]
    assert urine_expl.is_fallback is True
    assert urine_expl.what_it_measures == FALLBACK_UNAVAILABLE_MESSAGE


def test_llm_violation_triggers_automatic_template_fallback():
    """Simulate an LLM producing a diagnostic and medication violation, verifying fallback."""
    mock_llm = MagicMock()
    # Mock LLM returning forbidden terms: 'you have' and 'take 500 mg tablets'
    mock_llm.generate_structured.return_value = LLMTestResponse(
        what_it_measures="Hemoglobin carries oxygen.",
        what_your_value_means="Based on this low value, you have severe anemia. Please take 500 mg tablets of iron.",
        factors_that_can_affect_result=["Diet"],
        when_to_talk_to_doctor="Talk to doctor.",
        questions_for_doctor=["Why is it low?", "What diet?", "Should I retest?"],
    )

    explainer = LLMGroundedExplainer(llm_client=mock_llm)
    res = explainer.explain_test(
        test_name="Hemoglobin",
        value=10.5,
        unit="g/dL",
        reference_interval="13.0 - 17.0",
        flag="LOW",
    )

    # Output must NOT contain the forbidden text; it must have safely reverted to kb_template
    assert "you have severe anemia" not in res.what_your_value_means
    assert "500 mg" not in res.what_your_value_means
    # Verify it has the clean template explanation
    is_safe, violations = is_safe_explanation(res.what_your_value_means)
    assert is_safe is True
    assert len(violations) == 0
