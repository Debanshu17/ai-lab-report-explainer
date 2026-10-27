"""Tests for Hindi Localization (Phase 6).

Covers:
- 100% coverage of all 20 KB blood tests, categories, and direction terms in hindi_glossary.json.
- Strict Devanagari rules and Western number / Latin unit invariance verification.
- Detection of forbidden Devanagari numerals (०-९).
- Presence of Open Item #3 in-app unreviewed notice in all Hindi summaries.
- Verification of docs/hindi_review_packet.md generation and complete coverage.
"""

from pathlib import Path
import pytest

from src.data.loaders import load_knowledge_base
from src.explain.hindi import (
    load_hindi_glossary,
    verify_number_and_unit_invariance,
    HINDI_FLAG_LABELS,
    HINDI_UNREVIEWED_NOTICE,
)
from src.explain.templates import DeterministicTemplateExplainer
from src.safety.rules import is_safe_explanation, scan_for_forbidden_terms
from scripts.export_hindi_review import generate_hindi_review_packet


@pytest.fixture(scope="module")
def kb():
    return load_knowledge_base()


@pytest.fixture(scope="module")
def glossary():
    return load_hindi_glossary()


def test_glossary_covers_all_20_kb_tests(kb, glossary):
    """Verify that hindi_glossary.json covers 100% of curated blood tests."""
    tests_dict = glossary.get("tests", {})
    assert len(tests_dict) == 20

    for test in kb.blood_tests:
        tid = test.test_id
        assert tid in tests_dict, f"Missing test_id '{tid}' in Hindi glossary"
        entry = tests_dict[tid]
        assert entry["test_name_en"] == test.test_name
        assert entry["test_name_hi"] == test.test_name_hindi
        assert len(entry["test_name_hi"]) > 0
        assert entry["test_name_transliteration"] == test.test_name_transliteration
        assert entry["standard_unit"] == test.standard_unit


def test_glossary_covers_categories_and_directions(glossary):
    """Verify that all standard categories and direction terms have Hindi counterparts."""
    cats = glossary.get("categories", {})
    assert len(cats) >= 7
    for cat_en, cat_hi in cats.items():
        assert len(cat_hi) > 0

    dirs = glossary.get("directions", {})
    assert set(dirs.keys()) == {"NORMAL", "LOW", "HIGH", "NEEDS_REVIEW"}
    for d_key, d_hi in dirs.items():
        assert len(d_hi) > 0


def test_number_and_unit_invariance_clean():
    """Verify that compliant Hindi explanation with Western digits passes invariance checks."""
    valid_hindi = (
        "आपका हीमोग्लोबिन परिणाम 13.5 g/dL है जो सामान्य सीमा (13.0 - 17.0 g/dL) के भीतर है।"
    )
    is_valid, violations = verify_number_and_unit_invariance(
        hindi_text=valid_hindi,
        expected_values=[13.5],
        expected_units=["g/dL"],
    )
    assert is_valid is True
    assert len(violations) == 0


def test_number_and_unit_invariance_catches_devanagari_numerals():
    """Verify that forbidden Devanagari numerals (e.g. १३.५) are caught and rejected."""
    invalid_hindi = "आपका परिणाम १३.५ g/dL है।"
    is_valid, violations = verify_number_and_unit_invariance(
        hindi_text=invalid_hindi,
        expected_values=[13.5],
        expected_units=["g/dL"],
    )
    assert is_valid is False
    assert any("Devanagari numeral" in v for v in violations)


def test_number_and_unit_invariance_catches_missing_values_and_units():
    """Verify that missing expected values or units are detected."""
    corrupted_hindi = "आपका परिणाम बहुत अच्छा है।"
    is_valid, violations = verify_number_and_unit_invariance(
        hindi_text=corrupted_hindi,
        expected_values=[12.4],
        expected_units=["mg/dL"],
    )
    assert is_valid is False
    assert any("Expected numeric value '12.4' missing" in v for v in violations)
    assert any("Expected scientific unit 'mg/dL' missing" in v for v in violations)


def test_export_hindi_review_packet(kb):
    """Verify that docs/hindi_review_packet.md is generated with side-by-side review tables."""
    packet_path = Path("docs/hindi_review_packet.md")
    content = generate_hindi_review_packet(output_path=packet_path)
    assert packet_path.exists()
    assert len(content.splitlines()) > 300

    # Must contain all 20 test IDs and 5 topic IDs
    for test in kb.blood_tests:
        assert f"`{test.test_id}`" in content
        assert test.test_name_hindi in content

    for topic in kb.general_topics:
        assert f"`{topic.topic_id}`" in content


def test_hindi_report_explanation_end_to_end():
    """Verify complete Hindi report generation preserves safety, provenance, and numbers."""
    explainer = DeterministicTemplateExplainer()
    sample_rows = [
        {"name": "Hemoglobin", "value": 11.2, "unit": "g/dL", "reference_interval": "13.0 - 17.0", "flag": "LOW"},
        {"name": "Total Cholesterol", "value": 185.0, "unit": "mg/dL", "reference_interval": "< 200", "flag": "NORMAL"},
    ]

    report = explainer.explain_report(sample_rows, language="hi")
    assert report.language == "hi"
    assert "शैक्षणिक साधन है" in report.disclaimer
    # Verify unreviewed notice is surfaced
    assert HINDI_UNREVIEWED_NOTICE in report.summary

    for test_expl in report.tests:
        assert test_expl.language == "hi"
        # Invariance check
        is_valid, violations = verify_number_and_unit_invariance(
            hindi_text=test_expl.what_your_value_means,
            expected_values=[test_expl.observed_value],
            expected_units=[test_expl.unit],
        )
        assert is_valid is True, f"Invariance violations: {violations}"

        # Safety check
        full_text = f"{test_expl.what_it_measures} {test_expl.what_your_value_means} {test_expl.when_to_talk_to_doctor}"
        is_safe, safety_violations = is_safe_explanation(full_text)
        assert is_safe is True, f"Safety violations: {safety_violations}"
