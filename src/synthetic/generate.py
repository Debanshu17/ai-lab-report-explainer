"""Synthetic report generator producing 40 diverse laboratory test PDFs.

Adheres strictly to Phase 1 requirements:
- 15 CSV patients + 25 synthetic variants (including >= 5 fully normal reports)
- 4 balanced layouts (A, B, C, D)
- Split: exactly 12 DEV, 28 TEST (3 DEV and 7 TEST per layout)
- Deterministic random seed (seed=42)
- Printed aliases (SGPT, SGOT, Hb, TLC, PCV, S. Creatinine, BUN, Vit D 25-OH)
- One-sided ranges, sex-specific single-cell ranges, multi-tier ranges
- 2 qualitative non-KB tests (Urine Glucose, Urine Protein)
- Western and Indian digit formatting
- Alternate units with value and range conversion
- Multi-page reports with table break (at least 2 reports)
- Ground-truth JSON with exact page tracking and inclusive expected_flag
- manifest.csv index
"""

from __future__ import annotations

import csv
import json
import math
import random
import re
from pathlib import Path
from typing import Any, Optional

import pymupdf

from src.data.loaders import load_csv_lab_database, load_knowledge_base
from src.data.mapping import AliasResolver
from src.data.models import GroundTruthReport, GroundTruthRow, HeaderPII
from src.flagging.flagger import flag_test_result
from src.synthetic.formats import (
    compute_expected_flag,
    format_indian_number,
    format_western_number,
)
from src.synthetic.layouts import (
    render_layout_a,
    render_layout_b,
    render_layout_c,
    render_layout_d,
)

SEED = 42

FAKE_LABS = [
    {
        "name": "Apex Diagnostic Healthcare Labs",
        "address": "42 Ring Road, Defence Colony, New Delhi 110024",
        "phone": "+91 11 2468 1357",
    },
    {
        "name": "MetroPath Pathology & Imaging",
        "address": "Plot 104, SV Road, Bandra West, Mumbai 400050",
        "phone": "+91 22 2640 9876",
    },
    {
        "name": "CareWell Diagnostic Centre",
        "address": "15 Church Street, Ashok Nagar, Bengaluru 560001",
        "phone": "+91 80 4123 5678",
    },
    {
        "name": "Sterling Clinical Laboratories",
        "address": "77 Park Street, Park Circus, Kolkata 700016",
        "phone": "+91 33 2287 4321",
    },
]

FAKE_DOCTORS = [
    "Dr. R. Sharma, MD",
    "Dr. Anjali Mehta, MBBS, DNB",
    "Dr. Vikram Sen, MD (Path)",
    "Dr. Priya Nambiar, MD, FRCP",
    "Dr. K. S. Mukherjee, MBBS",
]

FAKE_PATIENT_NAMES = [
    ("Aarav Gupta", "Male", 32),
    ("Sneha Roy", "Female", 28),
    ("Rohan Deshmukh", "Male", 51),
    ("Meera Patel", "Female", 46),
    ("Kavita Iyer", "Female", 62),
    ("Devendra Prasad", "Male", 58),
    ("Pooja Nair", "Female", 35),
    ("Amitabh Verma", "Male", 41),
    ("Sunita Kulkarni", "Female", 55),
    ("Rajesh Bhatt", "Male", 38),
    ("Nisha Sen", "Female", 24),
    ("Farhan Khan", "Male", 49),
    ("Deepa Menon", "Female", 33),
    ("Harish Reddy", "Male", 67),
    ("Alka Saxena", "Female", 42),
    ("Vikram Choudhary", "Male", 29),
    ("Sangeeta Joshi", "Female", 53),
    ("Manoj Tiwari", "Male", 60),
    ("Geeta Aggarwal", "Female", 39),
    ("Kishore Kumar", "Male", 48),
    ("Divya Pillai", "Female", 27),
    ("Sanjay Hegde", "Male", 64),
    ("Preeti Kapoor", "Female", 31),
    ("Ashok Singhal", "Male", 52),
    ("Tarun Bose", "Male", 44),
]

CATEGORY_ORDER = {
    "Complete Blood Count (CBC)": 1,
    "Diabetic Profile": 2,
    "Lipid Profile": 3,
    "Liver Function Tests": 4,
    "Kidney Function Tests": 5,
    "Thyroid Profile": 6,
    "Vitamins & Minerals": 7,
    "Routine Urine Examination": 8,
}


def get_test_section(test_id: Optional[str]) -> str:
    """Map test_id to an authentic clinical panel section."""
    if not test_id:
        return "Routine Urine Examination"
    mapping = {
        "HEMOGLOBIN": "Complete Blood Count (CBC)",
        "WBC": "Complete Blood Count (CBC)",
        "PLATELETS": "Complete Blood Count (CBC)",
        "RBC": "Complete Blood Count (CBC)",
        "HEMATOCRIT": "Complete Blood Count (CBC)",
        "MCV": "Complete Blood Count (CBC)",
        "FASTING_GLUCOSE": "Diabetic Profile",
        "HBA1C": "Diabetic Profile",
        "TOTAL_CHOLESTEROL": "Lipid Profile",
        "LDL": "Lipid Profile",
        "HDL": "Lipid Profile",
        "TRIGLYCERIDES": "Lipid Profile",
        "CREATININE": "Kidney Function Tests",
        "UREA": "Kidney Function Tests",
        "ALT": "Liver Function Tests",
        "AST": "Liver Function Tests",
        "BILIRUBIN": "Liver Function Tests",
        "TSH": "Thyroid Profile",
        "VITAMIN_D": "Vitamins & Minerals",
        "VITAMIN_B12": "Vitamins & Minerals",
    }
    return mapping.get(test_id, "General Clinical Chemistry")


def generate_all_reports(
    output_dir: Path,
    seed: int = SEED,
) -> list[GroundTruthReport]:
    """Generate all 40 reports, manifest, and ground truth files."""
    random.seed(seed)
    reports_dir = output_dir / "reports"
    truth_dir = output_dir / "truth"
    reports_dir.mkdir(parents=True, exist_ok=True)
    truth_dir.mkdir(parents=True, exist_ok=True)

    csv_rows = load_csv_lab_database()
    kb = load_knowledge_base()
    resolver = AliasResolver(kb)

    # Group CSV rows by patient
    csv_by_patient: dict[str, list[Any]] = {}
    for r in csv_rows:
        csv_by_patient.setdefault(r.Patient_ID, []).append(r)

    # 40 reports layout and split assignment (10 of each layout: 3 DEV, 7 TEST)
    # Total 12 DEV, 28 TEST
    layout_schedule = []
    for layout in ["Layout_A", "Layout_B", "Layout_C", "Layout_D"]:
        for _ in range(3):
            layout_schedule.append((layout, "DEV"))
        for _ in range(7):
            layout_schedule.append((layout, "TEST"))

    # Deterministically shuffle the schedule so layout and split are well distributed
    random.shuffle(layout_schedule)

    manifest_entries: list[dict[str, Any]] = []
    ground_truth_reports: list[GroundTruthReport] = []

    # Identify tests by category for normal reports
    kb_tests_by_id = {t.test_id: t for t in kb.blood_tests}

    for rep_idx in range(1, 41):
        report_id = f"REPORT_{rep_idx:03d}"
        layout, split = layout_schedule[rep_idx - 1]
        lab_info = FAKE_LABS[(rep_idx - 1) % len(FAKE_LABS)]
        doctor = FAKE_DOCTORS[(rep_idx - 1) % len(FAKE_DOCTORS)]
        coll_date = f"2026-10-{(rep_idx % 20) + 1:02d}"
        rep_date = f"2026-10-{(rep_idx % 20) + 2:02d}"

        # 1. Determine patient identity and test set
        is_fully_normal = False
        patient_rows: list[dict[str, Any]] = []

        if rep_idx <= 15:
            # Derived from CSV patient P001..P015
            pid = f"P{rep_idx:03d}"
            base_rows = csv_by_patient[pid]
            p_name = base_rows[0].Patient_Name
            age = base_rows[0].Age
            gender = base_rows[0].Gender
            phone = f"+91 98{rep_idx:02d}0 {rep_idx:02d}123"

            for r in base_rows:
                tid = resolver.resolve_strict(r.Test_Name)
                patient_rows.append(
                    {
                        "canonical_test_id": tid,
                        "base_name": r.Test_Name,
                        "value": r.Observed_Value,
                        "unit": r.Unit,
                        "range_str": r.Reference_Interval,
                    }
                )
        elif 16 <= rep_idx <= 21:
            # Fully normal reports (6 reports >= 5 required)
            is_fully_normal = True
            name_tuple = FAKE_PATIENT_NAMES[(rep_idx - 16) % len(FAKE_PATIENT_NAMES)]
            p_name, gender, age = name_tuple
            pid = f"SYN_{rep_idx:03d}"
            phone = f"+91 97{rep_idx:02d}1 {rep_idx:02d}456"

            # 16-20 tests per normal report, values picked strictly at midpoint of normal ranges
            for tid, bt in kb_tests_by_id.items():
                if tid in {"HEMOGLOBIN", "RBC", "HEMATOCRIT", "CREATININE", "ALT", "AST", "HDL"}:
                    # Sex specific
                    if tid == "HEMOGLOBIN":
                        low, high = (13.8, 17.2) if gender == "Male" else (12.1, 15.1)
                    elif tid == "RBC":
                        low, high = (4.7, 6.1) if gender == "Male" else (4.2, 5.4)
                    elif tid == "HEMATOCRIT":
                        low, high = (40.7, 50.3) if gender == "Male" else (36.1, 44.3)
                    elif tid == "CREATININE":
                        low, high = (0.7, 1.3) if gender == "Male" else (0.6, 1.1)
                    elif tid == "ALT":
                        low, high = (10.0, 40.0) if gender == "Male" else (7.0, 35.0)
                    elif tid == "AST":
                        low, high = (10.0, 40.0) if gender == "Male" else (9.0, 32.0)
                    elif tid == "HDL":
                        low, high = (40.0, 60.0) if gender == "Male" else (50.0, 60.0)
                else:
                    ranges_map = {
                        "WBC": (4500.0, 11000.0),
                        "PLATELETS": (150000.0, 450000.0),
                        "MCV": (80.0, 100.0),
                        "FASTING_GLUCOSE": (70.0, 99.0),
                        "HBA1C": (4.0, 5.6),
                        "TOTAL_CHOLESTEROL": (125.0, 200.0),
                        "LDL": (50.0, 100.0),
                        "TRIGLYCERIDES": (30.0, 150.0),
                        "UREA": (7.0, 20.0),
                        "BILIRUBIN": (0.2, 1.2),
                        "TSH": (0.4, 4.0),
                        "VITAMIN_D": (30.0, 100.0),
                        "VITAMIN_B12": (200.0, 900.0),
                    }
                    low, high = ranges_map[tid]

                mid = round(low + (high - low) * 0.5, 2)
                # Keep whole number if both limits are integers
                if low.is_integer() and high.is_integer() and tid not in {"BILIRUBIN", "TSH", "CREATININE", "HBA1C"}:
                    mid = round(mid)

                range_str = f"{low}-{high}" if not (low.is_integer() and high.is_integer()) else f"{int(low)}-{int(high)}"
                patient_rows.append(
                    {
                        "canonical_test_id": tid,
                        "base_name": bt.test_name,
                        "value": mid,
                        "unit": bt.standard_unit,
                        "range_str": range_str,
                    }
                )
        else:
            # 22-40: Synthetic perturbed variants (subsets of 10-20 tests + urine non-KB tests)
            name_tuple = FAKE_PATIENT_NAMES[(rep_idx - 16) % len(FAKE_PATIENT_NAMES)]
            p_name, gender, age = name_tuple
            pid = f"SYN_{rep_idx:03d}"
            phone = f"+91 96{rep_idx:02d}2 {rep_idx:02d}789"

            # Select 12-20 tests
            sample_size = random.randint(14, 20)
            chosen_tids = random.sample(list(kb_tests_by_id.keys()), sample_size)

            for tid in chosen_tids:
                bt = kb_tests_by_id[tid]
                # Default ranges
                if tid in {"HEMOGLOBIN", "RBC", "HEMATOCRIT", "CREATININE", "ALT", "AST", "HDL"}:
                    if tid == "HEMOGLOBIN":
                        low, high = (13.8, 17.2) if gender == "Male" else (12.1, 15.1)
                    elif tid == "RBC":
                        low, high = (4.7, 6.1) if gender == "Male" else (4.2, 5.4)
                    elif tid == "HEMATOCRIT":
                        low, high = (40.7, 50.3) if gender == "Male" else (36.1, 44.3)
                    elif tid == "CREATININE":
                        low, high = (0.7, 1.3) if gender == "Male" else (0.6, 1.1)
                    elif tid == "ALT":
                        low, high = (10.0, 40.0) if gender == "Male" else (7.0, 35.0)
                    elif tid == "AST":
                        low, high = (10.0, 40.0) if gender == "Male" else (9.0, 32.0)
                    elif tid == "HDL":
                        low, high = (40.0, 60.0) if gender == "Male" else (50.0, 60.0)
                else:
                    ranges_map = {
                        "WBC": (4500.0, 11000.0),
                        "PLATELETS": (150000.0, 450000.0),
                        "MCV": (80.0, 100.0),
                        "FASTING_GLUCOSE": (70.0, 99.0),
                        "HBA1C": (4.0, 5.6),
                        "TOTAL_CHOLESTEROL": (125.0, 200.0),
                        "LDL": (50.0, 100.0),
                        "TRIGLYCERIDES": (30.0, 150.0),
                        "UREA": (7.0, 20.0),
                        "BILIRUBIN": (0.2, 1.2),
                        "TSH": (0.4, 4.0),
                        "VITAMIN_D": (30.0, 100.0),
                        "VITAMIN_B12": (200.0, 900.0),
                    }
                    low, high = ranges_map[tid]

                # Perturb value: 40% chance abnormal (low or high)
                roll = random.random()
                if roll < 0.2:
                    val = round(low * random.uniform(0.65, 0.95), 2)
                elif roll < 0.4:
                    val = round(high * random.uniform(1.05, 1.45), 2)
                else:
                    val = round(random.uniform(low, high), 2)

                if low.is_integer() and high.is_integer() and tid not in {"BILIRUBIN", "TSH", "CREATININE", "HBA1C"}:
                    val = round(val)

                range_str = f"{low}-{high}" if not (low.is_integer() and high.is_integer()) else f"{int(low)}-{int(high)}"
                patient_rows.append(
                    {
                        "canonical_test_id": tid,
                        "base_name": bt.test_name,
                        "value": val,
                        "unit": bt.standard_unit,
                        "range_str": range_str,
                    }
                )

        # 2. Add qualitative non-KB tests (e.g. Urine Glucose & Urine Protein) to test fallback
        if rep_idx % 3 == 0:
            patient_rows.append(
                {
                    "canonical_test_id": None,
                    "base_name": "Urine Glucose",
                    "value": None,
                    "val_text": "Negative",
                    "unit": "",
                    "range_str": "Negative",
                }
            )
            patient_rows.append(
                {
                    "canonical_test_id": None,
                    "base_name": "Urine Protein",
                    "value": None,
                    "val_text": "Nil",
                    "unit": "",
                    "range_str": "Nil",
                }
            )

        # 3. For multi-page reports: ensure at least 2 reports (e.g. reports 12, 25, 35) have 32+ rows to cleanly break across pages
        if rep_idx in {12, 25, 35}:
            extra_tids = list(kb_tests_by_id.keys()) + list(kb_tests_by_id.keys())
            for extra_tid in extra_tids:
                if len(patient_rows) < 34:
                    orig_match = next((p for p in patient_rows if p.get("canonical_test_id") == extra_tid), None)
                    if orig_match:
                        val_to_use = orig_match["value"]
                        rng_to_use = orig_match["range_str"]
                    else:
                        bt_info = kb_tests_by_id[extra_tid]
                        val_to_use = round(sum(bt_info.plausible_value_bounds) / 2.0, 1)
                        rng_to_use = "10-50"

                    patient_rows.append(
                        {
                            "canonical_test_id": extra_tid,
                            "base_name": f"Follow-up {kb_tests_by_id[extra_tid].test_name}",
                            "value": val_to_use,
                            "unit": kb_tests_by_id[extra_tid].standard_unit,
                            "range_str": rng_to_use,
                        }
                    )

        # 4. Apply realistic variations: aliases, formatting, one-sided ranges, multi-tier ranges
        formatted_rows: list[dict[str, Any]] = []
        abnormal_count = 0

        for r in patient_rows:
            tid = r["canonical_test_id"]
            val = r["value"]
            unit = r["unit"]
            range_str = r["range_str"]
            base_name = r["base_name"]

            # Aliases
            printed_name = base_name
            if tid == "ALT" and random.random() < 0.6:
                printed_name = random.choice(["SGPT", "ALT (SGPT)", "Alanine Aminotransferase"])
            elif tid == "AST" and random.random() < 0.6:
                printed_name = random.choice(["SGOT", "AST (SGOT)", "Aspartate Aminotransferase"])
            elif tid == "HEMOGLOBIN" and random.random() < 0.5:
                printed_name = random.choice(["Hb", "Haemoglobin", "Hemoglobin (Hb)"])
            elif tid == "WBC" and random.random() < 0.6:
                printed_name = random.choice(["TLC", "Total Leukocyte Count (TLC)", "White Blood Cells"])
            elif tid == "HEMATOCRIT" and random.random() < 0.5:
                printed_name = random.choice(["PCV", "Packed Cell Volume (PCV)", "Hematocrit (Hct)"])
            elif tid == "CREATININE" and random.random() < 0.6:
                printed_name = random.choice(["S. Creatinine", "Serum Creatinine", "Creatinine"])
            elif tid == "UREA" and random.random() < 0.5:
                printed_name = random.choice(["BUN", "Blood Urea Nitrogen", "Urea"])
            elif tid == "VITAMIN_D" and random.random() < 0.6:
                printed_name = random.choice(["Vit D 25-OH", "25-OH Vitamin D", "Vitamin D (Total)"])
            elif tid == "FASTING_GLUCOSE" and random.random() < 0.5:
                printed_name = random.choice(["Fasting Blood Sugar", "FBS", "Glucose, Fasting"])

            # Value string formatting (Western vs Indian grouping)
            if val is not None:
                if tid in {"PLATELETS", "WBC"} and rep_idx % 2 == 0:
                    val_text = format_indian_number(val)
                elif tid in {"PLATELETS", "WBC"}:
                    val_text = format_western_number(val)
                else:
                    val_text = str(val)
            else:
                val_text = r.get("val_text", "Negative")

            # One-sided ranges for some tests in Layouts A, B, D
            if not is_fully_normal and layout in {"Layout_A", "Layout_D"} and rep_idx % 4 == 0:
                if tid == "TOTAL_CHOLESTEROL":
                    range_str = "< 200"
                elif tid == "TRIGLYCERIDES":
                    range_str = "< 150"
                elif tid == "FASTING_GLUCOSE":
                    range_str = "< 100"
                elif tid == "HBA1C":
                    range_str = "< 5.7"
                elif tid == "HDL":
                    range_str = "> 40"
                elif tid == "TSH":
                    range_str = "Up to 4.0"

            # Multi-tier ranges in Layout D
            if not is_fully_normal and layout == "Layout_D":
                if tid == "TOTAL_CHOLESTEROL":
                    range_str = "Desirable <200, Borderline 200-239, High >=240"
                elif tid == "TRIGLYCERIDES":
                    range_str = "Normal <150, Borderline 150-199, High >=200"
                elif tid == "LDL":
                    range_str = "Optimal <100, Borderline 100-129, High >=130"

            # Single-cell sex-specific range in Layout B or C
            if not is_fully_normal and tid in {"HEMOGLOBIN", "RBC", "HEMATOCRIT"} and rep_idx % 3 == 0:
                if tid == "HEMOGLOBIN":
                    range_str = "M: 13.8-17.2 F: 12.1-15.1"
                elif tid == "RBC":
                    range_str = "M: 4.7-6.1 F: 4.2-5.4"
                elif tid == "HEMATOCRIT":
                    range_str = "M: 40.7-50.3 F: 36.1-44.3"

            # Alternate units (e.g. g/L for Hb, mmol/L for glucose/cholesterol) in some reports
            if not is_fully_normal and rep_idx % 5 == 0:
                if tid == "HEMOGLOBIN" and val is not None:
                    val = round(val * 10.0, 1)
                    val_text = str(val)
                    unit = "g/L"
                    range_str = "138-172" if gender == "Male" else "121-151"
                elif tid == "FASTING_GLUCOSE" and val is not None:
                    val = round(val * 0.0555, 2)
                    val_text = str(val)
                    unit = "mmol/L"
                    range_str = "3.9-5.5"

            # Compute expected flag strictly from printed range using flagger
            flag_res = flag_test_result(
                value=val,
                value_text=val_text,
                range_text=range_str,
                patient_sex=gender,
                test_id=tid,
                unit=unit,
                kb=kb,
            )
            flag = flag_res.flag
            range_type = flag_res.range_type
            r_low = flag_res.ref_low
            r_high = flag_res.ref_high

            if flag in {"LOW", "HIGH"}:
                abnormal_count += 1

            flag_marker = None
            if flag == "HIGH":
                flag_marker = "H"
            elif flag == "LOW":
                flag_marker = "L"

            section_name = get_test_section(tid)

            formatted_rows.append(
                {
                    "printed_name": printed_name,
                    "canonical_test_id": tid,
                    "value": val,
                    "printed_value_text": val_text,
                    "unit": unit,
                    "printed_range_text": range_str,
                    "range_type": range_type,
                    "ref_low": r_low,
                    "ref_high": r_high,
                    "expected_flag": flag,
                    "section": section_name,
                    "printed_flag_marker": flag_marker,
                    "page": 1,  # will update after PDF rendering
                }
            )

        # 5. Render PDF to disk
        pdf_filename = f"{report_id}.pdf"
        pdf_path = reports_dir / pdf_filename

        header_dict = {
            "lab_name": lab_info["name"],
            "lab_address": lab_info["address"],
            "lab_phone": lab_info["phone"],
            "patient_id": pid,
            "patient_name": p_name,
            "age": age,
            "gender": gender,
            "phone": phone,
            "doctor": doctor,
            "collection_date": coll_date,
            "report_date": rep_date,
        }

        if layout == "Layout_A":
            render_layout_a(pdf_path, header_dict, formatted_rows)
        elif layout == "Layout_B":
            render_layout_b(pdf_path, header_dict, formatted_rows)
        elif layout == "Layout_C":
            render_layout_c(pdf_path, header_dict, formatted_rows)
        elif layout == "Layout_D":
            render_layout_d(pdf_path, header_dict, formatted_rows)
        else:
            raise ValueError(f"Unknown layout: {layout}")

        # 6. Verify rendered PDF with PyMuPDF and detect exact page number per row
        doc = pymupdf.open(pdf_path)
        num_pages = len(doc)

        for r_item in formatted_rows:
            p_name_search = r_item["printed_name"]
            # Search which page contains this test
            for p_idx in range(num_pages):
                page_text = doc[p_idx].get_text()
                if p_name_search in page_text:
                    r_item["page"] = p_idx + 1
                    break
        doc.close()

        # 7. Construct and validate GroundTruthReport model
        gt_rows = [GroundTruthRow.model_validate(r) for r in formatted_rows]
        header_model = HeaderPII.model_validate(header_dict)

        gt_report = GroundTruthReport(
            report_id=report_id,
            filename=pdf_filename,
            layout=layout,
            split=split,
            header=header_model,
            rows=gt_rows,
        )
        ground_truth_reports.append(gt_report)

        # Save ground-truth JSON
        truth_json_path = truth_dir / f"{report_id}.json"
        with open(truth_json_path, mode="w", encoding="utf-8") as f:
            f.write(gt_report.model_dump_json(indent=2))

        # Add manifest entry
        manifest_entries.append(
            {
                "report_id": report_id,
                "filename": pdf_filename,
                "patient_id": pid,
                "patient_name": p_name,
                "age": age,
                "gender": gender,
                "layout": layout,
                "split": split,
                "num_tests": len(formatted_rows),
                "num_abnormal": abnormal_count,
                "is_fully_normal": is_fully_normal,
                "num_pages": num_pages,
            }
        )

    # 8. Write manifest.csv
    manifest_csv_path = output_dir / "manifest.csv"
    with open(manifest_csv_path, mode="w", encoding="utf-8", newline="") as f:
        fieldnames = [
            "report_id",
            "filename",
            "patient_id",
            "patient_name",
            "age",
            "gender",
            "layout",
            "split",
            "num_tests",
            "num_abnormal",
            "is_fully_normal",
            "num_pages",
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(manifest_entries)

    return ground_truth_reports


if __name__ == "__main__":
    out = Path("data/synthetic")
    print(f"Generating 40 synthetic lab reports in {out}...")
    reps = generate_all_reports(out)
    print(f"Successfully generated {len(reps)} reports!")
