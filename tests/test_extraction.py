"""Comprehensive unit tests for Phase 2: PDF validation, header stripping, extraction, and normalization."""

from __future__ import annotations

import io
from pathlib import Path
import pytest
import pymupdf

from src.extraction.llm_fallback import verify_verbatim_appearance
from src.extraction.normalize import (
    normalize_numeric_value,
    normalize_unit_string,
    resolve_alias_with_confidence,
)
from src.extraction.pipeline import extract_from_pdf_file, run_extraction_pipeline
from src.extraction.row_parser import _split_value_and_unit, extract_rows_from_pdf
from src.extraction.validate import ValidationError, validate_pdf_bytes
from src.privacy.header import detect_header_boundary, extract_patient_context_from_text
from src.privacy.redact import audit_payload_for_leaks, redact_pii_from_text


def test_validate_pdf_valid():
    """Verify that a standard synthetic report passes validation."""
    sample_pdf = Path("data/synthetic/reports/REPORT_001.pdf")
    res = validate_pdf_bytes(sample_pdf.read_bytes())
    assert res.is_valid is True
    assert res.num_pages >= 1
    assert res.total_characters > 100


def test_validate_pdf_empty():
    """Verify empty bytes raises ValidationError."""
    with pytest.raises(ValidationError, match="0 bytes") as exc:
        validate_pdf_bytes(b"")
    assert exc.value.code == "EMPTY_FILE"


def test_validate_pdf_not_pdf():
    """Verify non-PDF bytes raises ValidationError."""
    with pytest.raises(ValidationError, match="does not appear to be a valid PDF") as exc:
        validate_pdf_bytes(b"Not a PDF content at all")
    assert exc.value.code == "NOT_A_PDF"


def test_validate_pdf_too_large():
    """Verify exceeding max_size_mb raises ValidationError."""
    fake_header = b"%PDF-1.4 " + b"0" * 1024
    with pytest.raises(ValidationError, match="exceeds maximum limit") as exc:
        validate_pdf_bytes(fake_header, max_size_mb=0)  # threshold 0 MB
    assert exc.value.code == "FILE_TOO_LARGE"


def test_validate_pdf_scanned_detection():
    """Verify image-only/no-text PDF triggers the friendly scanned PDF error."""
    # Create a PDF with zero text (just a blank page)
    doc = pymupdf.open()
    doc.new_page()
    pdf_bytes = doc.tobytes()
    doc.close()

    with pytest.raises(ValidationError, match="Scanned reports are not supported yet") as exc:
        validate_pdf_bytes(pdf_bytes, min_char_threshold=50)
    assert exc.value.code == "SCANNED_PDF_NOT_SUPPORTED"


def test_extract_patient_context():
    """Verify non-PII clinical context extraction (age and gender only)."""
    header_sample = (
        "Patient: Vikram Sharma\n"
        "ID: P009\n"
        "Age/Sex: 45 Y / Male\n"
        "Ref By: Dr. Gupta\n"
        "Contact: +91 98765 43210\n"
    )
    age, gender = extract_patient_context_from_text(header_sample)
    assert age == 45
    assert gender == "Male"

    # Female format
    female_sample = "Patient: Sunita Sen | Age: 34 Years | Gender: Female"
    age_f, gender_f = extract_patient_context_from_text(female_sample)
    assert age_f == 34
    assert gender_f == "Female"


def test_redact_pii_from_text():
    """Verify phone, email, and patient identifiers are masked."""
    raw = "Patient: John Doe, Phone: +91 98010 01123, Doctor: Dr. R. Sharma, ID: P001 on 2026-10-02"
    redacted = redact_pii_from_text(raw)
    assert "[REDACTED_PHONE]" in redacted
    assert "+91 98010 01123" not in redacted
    assert "[REDACTED_NAME]" in redacted
    assert "[REDACTED_DOCTOR]" in redacted
    assert "[REDACTED_ID]" in redacted


def test_audit_payload_for_leaks():
    """Verify leak detection identifies forbidden strings."""
    forbidden = ["John Doe", "Defence Colony", "+91 11 2468 1357"]
    clean_payload = "Please explain the test Hemoglobin with value 14.8 g/dL."
    assert audit_payload_for_leaks(clean_payload, forbidden) == []

    leaky_payload = "Please explain test for John Doe living in Defence Colony."
    leaks = audit_payload_for_leaks(leaky_payload, forbidden)
    assert "John Doe" in leaks
    assert "Defence Colony" in leaks


def test_normalize_numeric_value():
    """Verify comma removal, trailing flag extraction, and qualitative detection."""
    # Western commas
    val, flag, qual = normalize_numeric_value("150,000")
    assert val == 150000.0
    assert flag is None
    assert qual is False

    # Indian commas
    val, flag, qual = normalize_numeric_value("1,50,000")
    assert val == 150000.0

    # Trailing flag
    val, flag, qual = normalize_numeric_value("142.7 H")
    assert val == 142.7
    assert flag == "H"

    val_l, flag_l, _ = normalize_numeric_value("3.2 L")
    assert val_l == 3.2
    assert flag_l == "L"

    # Qualitative
    val_q, flag_q, is_qual = normalize_numeric_value("Negative")
    assert val_q is None
    assert is_qual is True


def test_normalize_unit_string():
    """Verify unit normalizations."""
    assert normalize_unit_string("cells/ul") == "cells/µL"
    assert normalize_unit_string("cells/\u03bcL") == "cells/µL"
    assert normalize_unit_string("cumm") == "cells/µL"
    assert normalize_unit_string("g/dl") == "g/dL"
    assert normalize_unit_string("mg/dl") == "mg/dL"


def test_split_value_and_unit():
    """Verify splitting combined value cells."""
    v, u = _split_value_and_unit("55.0 mg/dL")
    assert v == "55.0"
    assert u == "mg/dL"

    v_c, u_c = _split_value_and_unit("6.0 million cells/µL")
    assert v_c == "6.0"
    assert u_c == "million cells/µL"


def test_verbatim_appearance_check():
    """Verify verbatim token matching against raw source row text."""
    source_row = "Haemoglobin | 14.8 | g/dL | 13.8 - 17.2"
    assert verify_verbatim_appearance("14.8", source_row) is True
    assert verify_verbatim_appearance("13.8-17.2", source_row) is True
    assert verify_verbatim_appearance("13.8 - 17.2", source_row) is True

    # Hallucinated value not in text
    assert verify_verbatim_appearance("15.2", source_row) is False
    assert verify_verbatim_appearance("10-20", source_row) is False


def test_extraction_pipeline_dev_sample_reports():
    """Verify end-to-end extraction pipeline on samples across all 4 layouts."""
    # Layout A
    res_a = extract_from_pdf_file("data/synthetic/reports/REPORT_001.pdf", mode="rules_only")
    assert res_a.total_rows == 20
    assert res_a.unparsed_rows == 0
    assert res_a.patient_context.gender == "Male"
    assert res_a.patient_context.age == 45

    # Layout B
    res_b = extract_from_pdf_file("data/synthetic/reports/REPORT_003.pdf", mode="rules_only")
    assert res_b.total_rows == 22
    assert res_b.unparsed_rows == 0

    # Layout C (Two-column)
    res_c = extract_from_pdf_file("data/synthetic/reports/REPORT_005.pdf", mode="rules_only")
    assert res_c.total_rows == 20
    assert res_c.unparsed_rows == 0

    # Layout D (Multi-tier)
    res_d = extract_from_pdf_file("data/synthetic/reports/REPORT_004.pdf", mode="rules_only")
    assert res_d.total_rows == 20
    assert res_d.unparsed_rows == 0
