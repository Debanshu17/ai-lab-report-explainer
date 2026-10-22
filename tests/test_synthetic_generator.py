"""Unit tests for Phase 1 synthetic report generator, layouts, formats, and ground truth."""

from __future__ import annotations

import csv
import json
from pathlib import Path
import pytest
import pymupdf

from src.data.models import GroundTruthReport
from src.synthetic.formats import compute_expected_flag, format_indian_number, format_western_number


def test_digit_formatters():
    """Verify Indian and Western digit grouping."""
    assert format_western_number(150000) == "150,000"
    assert format_western_number(4500) == "4,500"
    assert format_western_number(14.8) == "14.8"

    assert format_indian_number(150000) == "1,50,000"
    assert format_indian_number(4500) == "4,500"
    assert format_indian_number(1000000) == "10,00,000"
    assert format_indian_number(14.8) == "14.8"


def test_compute_expected_flag_inclusive_limits():
    """Verify limits are inclusive (value == limit is NORMAL)."""
    # Low limit exact match
    flag, r_type, low, high = compute_expected_flag(70.0, "70.0", "70-99")
    assert flag == "NORMAL"
    assert r_type == "between"
    assert low == 70.0
    assert high == 99.0

    # High limit exact match
    flag, r_type, low, high = compute_expected_flag(99.0, "99.0", "70-99")
    assert flag == "NORMAL"

    # Out of range low
    flag, _, _, _ = compute_expected_flag(69.9, "69.9", "70-99")
    assert flag == "LOW"

    # Out of range high
    flag, _, _, _ = compute_expected_flag(100.0, "100.0", "70-99")
    assert flag == "HIGH"


def test_compute_expected_flag_multi_tier():
    """Verify multi-tier ranges return NEEDS_REVIEW."""
    rng = "Desirable <200, Borderline 200-239, High >=240"
    flag, r_type, _, _ = compute_expected_flag(180.0, "180", rng)
    assert flag == "NEEDS_REVIEW"
    assert r_type == "multi_tier"


def test_compute_expected_flag_sex_specific():
    """Verify sex-specific range parsed from single cell."""
    rng = "M: 13.8-17.2 F: 12.1-15.1"
    # Male normal
    flag_m, _, low, high = compute_expected_flag(14.0, "14.0", rng, patient_sex="Male")
    assert flag_m == "NORMAL"
    assert low == 13.8
    assert high == 17.2

    # Female low for 11.5
    flag_f, _, low, high = compute_expected_flag(11.5, "11.5", rng, patient_sex="Female")
    assert flag_f == "LOW"
    assert low == 12.1
    assert high == 15.1

    # Missing sex -> NEEDS_REVIEW
    flag_none, _, _, _ = compute_expected_flag(14.0, "14.0", rng, patient_sex=None)
    assert flag_none == "NEEDS_REVIEW"


def test_manifest_dimensions_and_balance():
    """Verify manifest.csv has 40 reports, 12 DEV / 28 TEST, balanced across layouts."""
    manifest_path = Path("data/synthetic/manifest.csv")
    assert manifest_path.is_file()

    rows = []
    with open(manifest_path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(r)

    assert len(rows) == 40

    split_counts = {"DEV": 0, "TEST": 0}
    layout_counts = {"Layout_A": 0, "Layout_B": 0, "Layout_C": 0, "Layout_D": 0}
    split_by_layout = {l: {"DEV": 0, "TEST": 0} for l in layout_counts}
    fully_normal_count = 0
    multipage_count = 0

    for r in rows:
        split_counts[r["split"]] += 1
        layout_counts[r["layout"]] += 1
        split_by_layout[r["layout"]][r["split"]] += 1
        if r["is_fully_normal"].lower() == "true":
            fully_normal_count += 1
        if int(r["num_pages"]) > 1:
            multipage_count += 1

    assert split_counts["DEV"] == 12
    assert split_counts["TEST"] == 28

    for layout, count in layout_counts.items():
        assert count == 10, f"Layout {layout} count {count} != 10"
        assert split_by_layout[layout]["DEV"] == 3
        assert split_by_layout[layout]["TEST"] == 7

    assert fully_normal_count >= 5, f"Expected >= 5 fully normal, found {fully_normal_count}"
    assert multipage_count >= 2, f"Expected >= 2 multi-page reports, found {multipage_count}"


def test_ground_truth_json_schema():
    """Verify all 40 ground-truth JSON files parse into GroundTruthReport model."""
    truth_dir = Path("data/synthetic/truth")
    json_files = list(truth_dir.glob("*.json"))
    assert len(json_files) == 40

    for jf in json_files:
        data = json.loads(jf.read_text(encoding="utf-8"))
        report = GroundTruthReport.model_validate(data)
        assert len(report.rows) >= 10
        assert report.split in {"DEV", "TEST"}
        assert report.layout in {"Layout_A", "Layout_B", "Layout_C", "Layout_D"}
        for r in report.rows:
            assert r.page >= 1
            assert r.expected_flag in {"LOW", "HIGH", "NORMAL", "NEEDS_REVIEW"}


def test_pdf_extraction_and_micro_sign():
    """Verify PyMuPDF extracts text from all 40 PDFs and the micro sign survives."""
    reports_dir = Path("data/synthetic/reports")
    pdf_files = list(reports_dir.glob("*.pdf"))
    assert len(pdf_files) == 40

    micro_sign_found_total = 0

    for pdf_path in pdf_files:
        doc = pymupdf.open(pdf_path)
        assert len(doc) >= 1
        full_text = ""
        for page in doc:
            txt = page.get_text()
            assert len(txt.strip()) > 50  # Must contain extracted text
            full_text += txt
        doc.close()

        # Check for micro sign in text (WBC / Platelets use cells/µL or million cells/µL)
        if "\u00b5" in full_text or "\u03bc" in full_text:
            micro_sign_found_total += 1

        # Check Clinical_Context is NEVER printed
        for forbidden in ["Normal Checkup", "Anemia Profile", "Diabetic Evaluation", "Lipid Screening", "Clinical_Context"]:
            assert forbidden not in full_text, f"Forbidden label '{forbidden}' leaked onto {pdf_path.name}"

    assert micro_sign_found_total >= 30, f"Micro sign should survive in most reports, found in {micro_sign_found_total}"


def test_thumbnails_exist():
    """Verify that thumbnails were created for all 4 layouts."""
    thumb_dir = Path("data/synthetic/thumbnails")
    for layout in ["Layout_A", "Layout_B", "Layout_C", "Layout_D"]:
        thumb_file = thumb_dir / f"{layout}.png"
        assert thumb_file.is_file(), f"Missing thumbnail: {thumb_file}"
        assert thumb_file.stat().st_size > 1000  # Non-trivial image
