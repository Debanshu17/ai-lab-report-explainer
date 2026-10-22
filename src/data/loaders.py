"""Data loaders for CSV lab database and JSON Knowledge Base.

Enforces fail-loud validation on schema errors or missing files.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Union

from src.config import settings, get_logger
from src.data.models import CSVLabRow, KnowledgeBase

logger = get_logger(__name__)


def load_csv_lab_database(
    path: Union[Path, str, None] = None
) -> list[CSVLabRow]:
    """Load and validate the synthetic lab database CSV.

    Fails loudly if the file is missing, empty, or fails schema validation.
    """
    csv_path = Path(path) if path else settings.DATA_INPUTS_DIR / "ai_lab_report_database.csv"
    if not csv_path.is_file():
        raise FileNotFoundError(f"CSV database not found at: {csv_path}")

    rows: list[CSVLabRow] = []
    with open(csv_path, mode="r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError(f"CSV database at {csv_path} has no header row.")

        expected_fields = {
            "Patient_ID",
            "Patient_Name",
            "Age",
            "Gender",
            "Clinical_Context",
            "Test_Name",
            "Observed_Value",
            "Unit",
            "Reference_Interval",
        }
        actual_fields = set(reader.fieldnames)
        missing_fields = expected_fields - actual_fields
        if missing_fields:
            raise ValueError(f"CSV database missing required headers: {sorted(missing_fields)}")

        for idx, raw_row in enumerate(reader, start=2):
            try:
                row = CSVLabRow.model_validate(raw_row)
                rows.append(row)
            except Exception as exc:
                raise ValueError(
                    f"Validation failed on line {idx} in {csv_path}: {exc}"
                ) from exc

    if not rows:
        raise ValueError(f"CSV database at {csv_path} contains 0 data rows.")

    logger.info("Successfully loaded %d lab rows from %s", len(rows), csv_path)
    return rows


def load_knowledge_base(
    path: Union[Path, str, None] = None
) -> KnowledgeBase:
    """Load and validate the curated Knowledge Base JSON.

    Fails loudly if the file is missing, invalid JSON, or fails schema validation.
    """
    kb_path = Path(path) if path else settings.DATA_INPUTS_DIR / "ai_lab_report_knowledge_base_final.json"
    if not kb_path.is_file():
        raise FileNotFoundError(f"Knowledge Base JSON not found at: {kb_path}")

    try:
        with open(kb_path, mode="r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in Knowledge Base file {kb_path}: {exc}") from exc

    try:
        kb = KnowledgeBase.model_validate(data)
    except Exception as exc:
        raise ValueError(f"Knowledge Base schema validation failed: {exc}") from exc

    logger.info(
        "Successfully loaded Knowledge Base: %d blood tests, %d general topics from %s",
        len(kb.blood_tests),
        len(kb.general_topics),
        kb_path,
    )
    return kb
