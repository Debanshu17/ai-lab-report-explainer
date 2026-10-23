"""Comprehensive unit and property tests for Phase 3 deterministic flagging engine."""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path
import pytest
from hypothesis import given, strategies as st

from src.data.loaders import load_csv_lab_database, load_knowledge_base
from src.data.models import GroundTruthReport
from src.flagging.flagger import flag_test_result, FlaggingResult
from src.flagging.range_parser import parse_reference_range
from src.flagging.units import (
    convert_hba1c_mmol_mol_to_percent,
    convert_hba1c_percent_to_mmol_mol,
    check_unit_compatibility,
)


# ----------------------------------------------------------------------
# 1. Table-driven tests for every range format
# ----------------------------------------------------------------------
@pytest.mark.parametrize(
    "val,val_text,range_str,expected_flag",
    [
        # Standard between: 13.0 - 17.0
        (12.9, "12.9", "13.0 - 17.0", "LOW"),
        (13.0, "13.0", "13.0 - 17.0", "NORMAL"),  # Low limit inclusive
        (15.0, "15.0", "13.0 - 17.0", "NORMAL"),
        (17.0, "17.0", "13.0 - 17.0", "NORMAL"),  # High limit inclusive
        (17.1, "17.1", "13.0 - 17.0", "HIGH"),
        # Dash variants and 'to' keyword
        (13.0, "13.0", "13.0 to 17.0", "NORMAL"),
        (10.0, "10.0", "13.0 – 17.0", "LOW"),  # En-dash
        (18.0, "18.0", "13.0 — 17.0", "HIGH"),  # Em-dash
        # Upper bound one-sided
        (199.0, "199.0", "< 200", "NORMAL"),
        (200.0, "200.0", "< 200", "NORMAL"),  # Limit inclusive
        (201.0, "201.0", "< 200", "HIGH"),
        (1.2, "1.2", "<= 1.2", "NORMAL"),
        (1.3, "1.3", "<= 1.2", "HIGH"),
        (4.5, "4.5", "Up to 5.0", "NORMAL"),
        (5.0, "5.0", "Up to 5.0", "NORMAL"),
        (5.5, "5.5", "Up to 5.0", "HIGH"),
        # Lower bound one-sided
        (39.0, "39.0", "> 40", "LOW"),
        (40.0, "40.0", "> 40", "NORMAL"),  # Limit inclusive
        (45.0, "45.0", "> 40", "NORMAL"),
        (50.0, "50.0", ">= 50", "NORMAL"),
        (49.9, "49.9", ">= 50", "LOW"),
        # Qualitative
        (None, "Negative", "Negative", "NORMAL"),
        (None, "Nil", "Nil", "NORMAL"),
        (None, "Non-reactive", "Non-reactive", "NORMAL"),
        (None, "Positive", "Negative", "HIGH"),
        # Multi-tier
        (180.0, "180.0", "Desirable <200, Borderline 200-239, High >=240", "NEEDS_REVIEW"),
        (140.0, "140.0", "Normal <150, Borderline 150-199, High >=200", "NEEDS_REVIEW"),
        # Unparseable or empty
        (10.0, "10.0", "Unknown Interval Text", "NEEDS_REVIEW"),
        (10.0, "10.0", "", "NEEDS_REVIEW"),
    ],
)
def test_table_driven_range_formats(val, val_text, range_str, expected_flag):
    res = flag_test_result(value=val, value_text=val_text, range_text=range_str)
    assert res.flag == expected_flag


def test_sex_specific_single_cell_flagging():
    """Verify sex-specific range parsed from single cell with sex dispatch."""
    rng = "M: 13.8-17.2 F: 12.1-15.1"

    # Male
    assert flag_test_result(13.8, "13.8", rng, patient_sex="Male").flag == "NORMAL"
    assert flag_test_result(13.7, "13.7", rng, patient_sex="Male").flag == "LOW"
    assert flag_test_result(17.2, "17.2", rng, patient_sex="Male").flag == "NORMAL"
    assert flag_test_result(17.3, "17.3", rng, patient_sex="Male").flag == "HIGH"

    # Female
    assert flag_test_result(12.1, "12.1", rng, patient_sex="Female").flag == "NORMAL"
    assert flag_test_result(12.0, "12.0", rng, patient_sex="Female").flag == "LOW"
    assert flag_test_result(15.1, "15.1", rng, patient_sex="Female").flag == "NORMAL"
    assert flag_test_result(15.2, "15.2", rng, patient_sex="Female").flag == "HIGH"

    # Sex missing -> NEEDS_REVIEW
    res_no_sex = flag_test_result(14.0, "14.0", rng, patient_sex=None)
    assert res_no_sex.flag == "NEEDS_REVIEW"


# ----------------------------------------------------------------------
# 2. Hypothesis Property-Based Testing for Inclusive Boundaries
# ----------------------------------------------------------------------
@given(
    low=st.floats(min_value=0.1, max_value=1000.0, allow_nan=False, allow_infinity=False),
    span=st.floats(min_value=0.1, max_value=500.0, allow_nan=False, allow_infinity=False),
)
def test_hypothesis_inclusive_boundaries(low: float, span: float):
    """Property test proving inclusive boundaries hold for all arbitrary numerical ranges."""
    low_val = round(low, 2)
    span_val = round(span, 2)
    high_val = round(low_val + span_val, 2)
    if high_val <= low_val:
        high_val = low_val + 0.1
    range_str = f"{low_val} - {high_val}"

    # 1. Exact lower limit must be NORMAL
    res_low = flag_test_result(value=low_val, value_text=str(low_val), range_text=range_str)
    assert res_low.flag == "NORMAL"

    # 2. Exact upper limit must be NORMAL
    res_high = flag_test_result(value=high_val, value_text=str(high_val), range_text=range_str)
    assert res_high.flag == "NORMAL"

    # 3. Value below lower limit must be LOW
    val_below = round(low_val - 0.05, 3)
    res_below = flag_test_result(value=val_below, value_text=str(val_below), range_text=range_str)
    assert res_below.flag == "LOW"

    # 4. Value above upper limit must be HIGH
    val_above = round(high_val + 0.05, 3)
    res_above = flag_test_result(value=val_above, value_text=str(val_above), range_text=range_str)
    assert res_above.flag == "HIGH"


# ----------------------------------------------------------------------
# 3. 15 CSV Boundary Rows as Direct Fixtures
# ----------------------------------------------------------------------
def test_all_15_csv_boundary_rows_flag_normal():
    """Verify all 15 boundary rows from ai_lab_report_database.csv evaluate to NORMAL."""
    rows = load_csv_lab_database()
    boundary_rows = []

    for r in rows:
        parts = [float(p.strip()) for p in r.Reference_Interval.split("-")]
        if r.Observed_Value == parts[0] or r.Observed_Value == parts[1]:
            boundary_rows.append(r)

    assert len(boundary_rows) == 15

    for r in boundary_rows:
        res = flag_test_result(
            value=r.Observed_Value,
            value_text=str(r.Observed_Value),
            range_text=r.Reference_Interval,
            patient_sex=r.Gender,
        )
        assert res.flag == "NORMAL", (
            f"CSV boundary row failed inclusive normal check: "
            f"Patient={r.Patient_ID}, Test={r.Test_Name}, Value={r.Observed_Value}, Range={r.Reference_Interval}"
        )


# ----------------------------------------------------------------------
# 4. Safety Guard: Static Test That Flagging Package Never Reads typical_range_info
# ----------------------------------------------------------------------
def test_flagging_package_never_reads_typical_range_info():
    """Enforce Core Principle 2: typical_range_info must NEVER be accessed in code for flagging."""
    import ast

    flagging_dir = Path("src/flagging")
    py_files = list(flagging_dir.glob("*.py"))
    assert len(py_files) >= 3

    for py_file in py_files:
        tree = ast.parse(py_file.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr == "typical_range_info":
                pytest.fail(
                    f"VIOLATION: AST Attribute access to 'typical_range_info' detected "
                    f"in {py_file.name} line {node.lineno}!"
                )
            if isinstance(node, ast.Name) and node.id == "typical_range_info":
                pytest.fail(
                    f"VIOLATION: Identifier access to 'typical_range_info' detected "
                    f"in {py_file.name} line {node.lineno}!"
                )


# ----------------------------------------------------------------------
# 5. Clinical Plausibility Bounds Check
# ----------------------------------------------------------------------
def test_clinical_implausibility_bounds():
    """Verify implausible values outside KB plausible_value_bounds trigger NEEDS_REVIEW."""
    kb = load_knowledge_base()

    # Hemoglobin bounds are [3.0, 25.0]
    # Implausibly low: 1.5 g/dL
    res_low = flag_test_result(
        value=1.5,
        value_text="1.5",
        range_text="13.8 - 17.2",
        test_id="HEMOGLOBIN",
        unit="g/dL",
        kb=kb,
    )
    assert res_low.flag == "NEEDS_REVIEW"
    assert res_low.is_implausible is True

    # Implausibly high: 50.0 g/dL
    res_high = flag_test_result(
        value=50.0,
        value_text="50.0",
        range_text="13.8 - 17.2",
        test_id="HEMOGLOBIN",
        unit="g/dL",
        kb=kb,
    )
    assert res_high.flag == "NEEDS_REVIEW"
    assert res_high.is_implausible is True


# ----------------------------------------------------------------------
# 6. Units Validation and HbA1c Formula Tests
# ----------------------------------------------------------------------
def test_hba1c_formula_conversions():
    """Verify official IFCC HbA1c conversion formula."""
    # 5.0% -> (5.0 - 2.15) * 10.93 = 31.1 mmol/mol
    mmol = convert_hba1c_percent_to_mmol_mol(5.0)
    assert math.isclose(mmol, 31.1, abs_tol=0.2)

    # Reverse: 31.1 mmol/mol -> ~5.0%
    pct = convert_hba1c_mmol_mol_to_percent(mmol)
    assert math.isclose(pct, 5.0, abs_tol=0.05)


def test_unit_compatibility_warnings():
    """Verify unit compatibility validation against KB."""
    # Standard unit
    compat_std, warn_std = check_unit_compatibility("HEMOGLOBIN", "g/dL")
    assert compat_std is True
    assert warn_std is None

    # Alternate unit in KB
    compat_alt, warn_alt = check_unit_compatibility("HEMOGLOBIN", "g/L")
    assert compat_alt is True
    assert warn_alt is None

    # Unexpected unit
    compat_bad, warn_bad = check_unit_compatibility("HEMOGLOBIN", "mg/dL")
    assert compat_bad is False
    assert warn_bad is not None
    assert "differs from standard" in warn_bad


# ----------------------------------------------------------------------
# 7. 100% Agreement Cross-Check with Ground-Truth Expected Flags
# ----------------------------------------------------------------------
def test_100_percent_agreement_with_ground_truth_all_40_reports():
    """Cross-check that flagger agrees 100% with expected_flag on all rows across all 40 reports."""
    truth_dir = Path("data/synthetic/truth")
    truth_files = list(truth_dir.glob("*.json"))
    assert len(truth_files) == 40

    kb = load_knowledge_base()
    total_checked = 0
    mismatches = []

    for jf in truth_files:
        data = json.loads(jf.read_text(encoding="utf-8"))
        report = GroundTruthReport.model_validate(data)
        patient_sex = report.header.gender

        for r in report.rows:
            total_checked += 1
            flagger_res = flag_test_result(
                value=r.value,
                value_text=r.printed_value_text,
                range_text=r.printed_range_text,
                patient_sex=patient_sex,
                test_id=r.canonical_test_id,
                unit=r.unit,
                kb=kb,
            )

            if flagger_res.flag != r.expected_flag:
                mismatches.append(
                    f"{report.report_id} | {r.printed_name} | Val: {r.value} ({r.printed_value_text}) | "
                    f"Range: {r.printed_range_text} | Flagger: {flagger_res.flag} != GT: {r.expected_flag}"
                )

    assert len(mismatches) == 0, (
        f"Detected {len(mismatches)} mismatches out of {total_checked} rows:\n" + "\n".join(mismatches[:10])
    )
    print(f"Verified 100% agreement across all {total_checked} rows in 40 reports!")
