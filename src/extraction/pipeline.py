"""Unified extraction pipeline coordinating validation, header stripping, rules, and LLM fallback.

Supports three selectable modes:
1. rules_only
2. llm_only
3. rules_plus_verified_llm (default)
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import List, Optional, Union
from pydantic import BaseModel, Field

import pymupdf

from src.config import settings, get_logger
from src.data.mapping import AliasResolver
from src.extraction.llm_fallback import fallback_extract_row_with_llm
from src.extraction.normalize import NormalizedTestRow, normalize_raw_row
from src.extraction.row_parser import RawExtractedRow, extract_rows_from_pdf
from src.extraction.validate import ValidationResult, validate_pdf_bytes
from src.privacy.header import SanitizedPatientContext, detect_header_boundary

logger = get_logger(__name__)


class ExtractionPipelineResult(BaseModel):
    """Complete structured output of the PDF extraction phase."""

    validation: ValidationResult
    patient_context: SanitizedPatientContext
    rows: List[NormalizedTestRow]
    total_rows: int
    parsed_rows: int
    unparsed_rows: int
    mode_used: str


def run_extraction_pipeline(
    pdf_bytes: bytes,
    mode: Optional[str] = None,
    resolver: Optional[AliasResolver] = None,
) -> ExtractionPipelineResult:
    """Execute end-to-end PDF validation, header stripping, and test row extraction."""
    selected_mode = mode or settings.EXTRACTION_MODE
    logger.info("Executing extraction pipeline under mode: %s", selected_mode)

    # 1. Validation check
    val_res = validate_pdf_bytes(pdf_bytes)

    # 2. Extract non-PII patient context (age/sex) from header
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    try:
        patient_ctx = detect_header_boundary(doc[0])
    finally:
        doc.close()

    # 3. Extract raw rows from tables or text lines
    raw_rows = extract_rows_from_pdf(pdf_bytes)
    res = resolver or AliasResolver()

    # 4. Process rows according to extraction mode
    final_rows: List[NormalizedTestRow] = []

    for raw in raw_rows:
        if selected_mode == "llm_only":
            normalized = fallback_extract_row_with_llm(
                source_row_text=raw.source_row_text,
                page=raw.page,
                section=raw.section,
            )
        elif selected_mode == "rules_only":
            normalized = normalize_raw_row(
                raw_name=raw.raw_test_name,
                raw_val_str=raw.raw_value_text,
                raw_unit_str=raw.raw_unit_str,
                raw_range_str=raw.raw_range_str,
                page=raw.page,
                section=raw.section,
                resolver=res,
            )
        elif selected_mode == "rules_plus_verified_llm":
            if raw.needs_llm_fallback or not raw.raw_value_text or not raw.raw_range_str:
                normalized = fallback_extract_row_with_llm(
                    source_row_text=raw.source_row_text,
                    page=raw.page,
                    section=raw.section,
                )
            else:
                normalized = normalize_raw_row(
                    raw_name=raw.raw_test_name,
                    raw_val_str=raw.raw_value_text,
                    raw_unit_str=raw.raw_unit_str,
                    raw_range_str=raw.raw_range_str,
                    page=raw.page,
                    section=raw.section,
                    resolver=res,
                )
        else:
            raise ValueError(f"Unknown extraction mode: {selected_mode}")

        final_rows.append(normalized)

    unparsed_cnt = sum(1 for r in final_rows if r.is_unparsed)
    parsed_cnt = len(final_rows) - unparsed_cnt

    return ExtractionPipelineResult(
        validation=val_res,
        patient_context=patient_ctx,
        rows=final_rows,
        total_rows=len(final_rows),
        parsed_rows=parsed_cnt,
        unparsed_rows=unparsed_cnt,
        mode_used=selected_mode,
    )


def extract_from_pdf_file(
    file_path: Union[Path, str],
    mode: Optional[str] = None,
) -> ExtractionPipelineResult:
    """Convenience helper to extract directly from a PDF file path."""
    path = Path(file_path)
    return run_extraction_pipeline(path.read_bytes(), mode=mode)
