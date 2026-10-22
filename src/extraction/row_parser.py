"""Table row reconstruction from digital PDF documents using pdfplumber and PyMuPDF.

Reconstructs lab test rows without hardcoding layout names.
Detects column headers dynamically, handles multi-line cells, section headers,
repeated headers, and multi-page table splits.
"""

from __future__ import annotations

import io
import re
from typing import List, Optional
from pydantic import BaseModel, Field

import pdfplumber
import pymupdf

from src.extraction.words import extract_page_words, cluster_words_into_lines
from src.privacy.header import detect_header_boundary


class RawExtractedRow(BaseModel):
    """Raw unparsed row extracted from table or text coordinates."""

    raw_test_name: str
    raw_value_text: str
    raw_unit_str: str
    raw_range_str: str
    page: int
    section: Optional[str] = None
    source_row_text: str
    needs_llm_fallback: bool = False


def _split_value_and_unit(text: str) -> tuple[str, str]:
    """Separate numeric/qualitative value from attached unit if column was combined.

    Examples:
        '55.0 mg/dL' -> ('55.0', 'mg/dL')
        '6.0 million cells/µL' -> ('6.0', 'million cells/µL')
        '48.0 %' -> ('48.0', '%')
        'Negative' -> ('Negative', '')
    """
    clean = text.strip()
    # Match value token (number with commas or qualitative word) followed by remainder
    m = re.match(r"^([0-9.,]+|[A-Za-z]+)\s*(.*)$", clean)
    if m:
        val = m.group(1).strip()
        unit = m.group(2).strip()
        return val, unit
    return clean, ""


def _is_section_header(cells: list[str]) -> bool:
    """Check if a table row represents a section subheader rather than a test result."""
    non_empty = [c for c in cells if c.strip()]
    if len(non_empty) == 1:
        txt = non_empty[0]
        # Section headers typically have no numeric values or units
        if not re.search(r"\d", txt) and not any(u in txt.lower() for u in ["mg/dl", "g/dl", "%", "cells"]):
            return True
    return False


def _is_table_column_header(cells: list[str]) -> bool:
    """Check if row contains table column titles (Test, Result, Unit, Range)."""
    joined = " ".join(cells).lower()
    has_test = any(k in joined for k in ["test", "parameter", "investigation", "analyte", "specification"])
    has_val_or_range = any(
        k in joined for k in ["result", "observed", "value", "unit", "reference", "range", "interval", "biological"]
    )
    return has_test and has_val_or_range


def extract_rows_with_pdfplumber(pdf_bytes: bytes) -> List[RawExtractedRow]:
    """Extract table rows dynamically across all pages using pdfplumber."""
    extracted: List[RawExtractedRow] = []
    current_section: Optional[str] = None

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for p_idx, page in enumerate(pdf.pages, start=1):
            tables = page.extract_tables()
            for table in tables:
                col_test_idx: int = 0
                col_val_idx: int = 1
                col_unit_idx: Optional[int] = None
                col_range_idx: int = 2
                col_flag_idx: Optional[int] = None

                for row in table:
                    if not row:
                        continue

                    # Clean each cell: collapse newlines inside cells into spaces
                    cells = [re.sub(r"\s+", " ", c).strip() if c else "" for c in row]
                    if not any(cells):
                        continue

                    # Filter out patient demographics table
                    if any("patient:" in c.lower() or "collected:" in c.lower() for c in cells):
                        continue

                    # Detect column header row and calibrate column indices
                    if _is_table_column_header(cells):
                        for i, col_txt in enumerate(cells):
                            c_low = col_txt.lower()
                            if any(k in c_low for k in ["test", "parameter", "investigation", "analyte", "specification"]):
                                col_test_idx = i
                            elif any(k in c_low for k in ["result", "observed", "value", "finding", "patient"]):
                                col_val_idx = i
                            elif "flag" in c_low:
                                col_flag_idx = i
                            elif "unit" in c_low:
                                col_unit_idx = i
                            elif any(k in c_low for k in ["reference", "interval", "range", "biological", "criteria"]):
                                col_range_idx = i
                        continue

                    # Detect section subheader
                    if _is_section_header(cells):
                        current_section = [c for c in cells if c][0]
                        continue

                    # Extract columns based on calibrated indices
                    t_name = cells[col_test_idx] if col_test_idx < len(cells) else ""
                    t_val = cells[col_val_idx] if col_val_idx < len(cells) else ""
                    t_unit = cells[col_unit_idx] if (col_unit_idx is not None and col_unit_idx < len(cells)) else ""
                    t_range = cells[col_range_idx] if col_range_idx < len(cells) else ""

                    # If unit column is absent, split unit from combined value cell (e.g. Layout C)
                    if not t_unit and t_val:
                        t_val, t_unit = _split_value_and_unit(t_val)

                    source_text = " | ".join(c for c in cells if c)

                    # Validate row viability
                    if t_name and (t_val or t_range):
                        needs_llm = not t_val or not t_range
                        extracted.append(
                            RawExtractedRow(
                                raw_test_name=t_name,
                                raw_value_text=t_val,
                                raw_unit_str=t_unit,
                                raw_range_str=t_range,
                                page=p_idx,
                                section=current_section,
                                source_row_text=source_text,
                                needs_llm_fallback=needs_llm,
                            )
                        )

    return extracted


def extract_rows_from_pdf(pdf_bytes: bytes) -> List[RawExtractedRow]:
    """Primary extraction entry point.

    Attempts structured table extraction via pdfplumber; falls back to
    coordinate clustering via PyMuPDF if no tables are detected.
    """
    rows = extract_rows_with_pdfplumber(pdf_bytes)
    if rows:
        return rows

    # Fallback to PyMuPDF coordinate clustering if pdfplumber finds no tables
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    extracted_fallback: List[RawExtractedRow] = []

    try:
        for p_idx, page in enumerate(doc, start=1):
            ctx = detect_header_boundary(page) if p_idx == 1 else None
            cutoff_y = ctx.header_boundary_y if ctx else 0.0

            words = extract_page_words(page, p_idx)
            table_words = [w for w in words if w.y0 > cutoff_y]
            lines = cluster_words_into_lines(table_words)

            for l in lines:
                text = l.line_text.strip()
                if not text or len(text) < 4:
                    continue
                # Skip header lines
                if _is_table_column_header([text]):
                    continue
                # Mark line for rule/llm parsing
                extracted_fallback.append(
                    RawExtractedRow(
                        raw_test_name=text,
                        raw_value_text="",
                        raw_unit_str="",
                        raw_range_str="",
                        page=p_idx,
                        source_row_text=text,
                        needs_llm_fallback=True,
                    )
                )
    finally:
        doc.close()

    return extracted_fallback
