"""Script to generate blank ground-truth label templates for real-world report evaluation.

Reads each PDF in data/real_reports/ and creates a matching CSV template in data/real_labels/
with columns: test_name, value, unit, printed_range, expected_flag.

Strict Privacy Guard:
- 100% offline; zero network calls.
- Never prints, logs, or sends report contents to an LLM.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

REAL_REPORTS_DIR = PROJECT_ROOT / "data" / "real_reports"
REAL_LABELS_DIR = PROJECT_ROOT / "data" / "real_labels"

CSV_FIELDNAMES = ["test_name", "value", "unit", "printed_range", "expected_flag"]


def create_templates(overwrite: bool = False) -> None:
    REAL_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    REAL_LABELS_DIR.mkdir(parents=True, exist_ok=True)

    pdf_files = sorted(list(REAL_REPORTS_DIR.glob("*.pdf")))

    if not pdf_files:
        print("[INFO] No PDFs found in data/real_reports/.")
        print("       Place real patient PDFs in 'data/real_reports/' to generate templates.")
        
        # Create an example blank template for reference
        example_csv = REAL_LABELS_DIR / "template_example.csv"
        if not example_csv.exists() or overwrite:
            with open(example_csv, mode="w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES)
                writer.writeheader()
                writer.writerow({
                    "test_name": "Hemoglobin",
                    "value": "14.2",
                    "unit": "g/dL",
                    "printed_range": "13.0-17.0",
                    "expected_flag": "NORMAL",
                })
                writer.writerow({
                    "test_name": "Platelet Count",
                    "value": "120000",
                    "unit": "cells/µL",
                    "printed_range": "150000-450000",
                    "expected_flag": "LOW",
                })
            print(f"[CREATED] Example reference template at: {example_csv.relative_to(PROJECT_ROOT)}")
        return

    created_count = 0
    skipped_count = 0

    for pdf in pdf_files:
        csv_filename = f"{pdf.stem}.csv"
        csv_path = REAL_LABELS_DIR / csv_filename

        if csv_path.exists() and not overwrite:
            print(f"[SKIP] Label CSV already exists: {csv_path.relative_to(PROJECT_ROOT)}")
            skipped_count += 1
            continue

        with open(csv_path, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES)
            writer.writeheader()
            # Provide 5 blank placeholder rows for manual entry
            for _ in range(5):
                writer.writerow({col: "" for col in CSV_FIELDNAMES})

        print(f"[CREATED] Blank label template: {csv_path.relative_to(PROJECT_ROOT)}")
        created_count += 1

    print(f"\nCompleted: {created_count} templates created, {skipped_count} skipped.")
    print("Fill in each CSV with the ground-truth values printed on each real report.")


if __name__ == "__main__":
    force_overwrite = "--overwrite" in sys.argv
    create_templates(overwrite=force_overwrite)
