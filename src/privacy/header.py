"""Header block detection and patient context extraction.

Extracts only non-PII clinical parameters (age and gender) necessary
for selecting sex-specific reference ranges.
"""

from __future__ import annotations

import re
from typing import Optional, Tuple
from pydantic import BaseModel, Field

import pymupdf


class SanitizedPatientContext(BaseModel):
    """Patient clinical parameters stripped of all identifying PII."""

    age: Optional[int] = Field(default=None, description="Patient age in years")
    gender: Optional[str] = Field(default=None, description="'Male' or 'Female'")
    header_boundary_y: float = Field(
        default=0.0, description="Bottom y-coordinate of the header region on Page 1"
    )


def extract_patient_context_from_text(text: str) -> Tuple[Optional[int], Optional[str]]:
    """Extract age and gender from raw header text."""
    age: Optional[int] = None
    gender: Optional[str] = None

    # 1. Combined pattern: "Age/Sex: 45 Y / Male" or "45 Years / Female"
    combined = re.search(
        r"(?:Age\s*[/,&]\s*(?:Sex|Gender)|Age)\s*[:=]?\s*(\d{1,3})\s*(?:Y(?:ears?|rs?)?)?\s*[/,\s]+\s*(Male|Female|M|F)\b",
        text,
        re.IGNORECASE,
    )
    if combined:
        age = int(combined.group(1))
        g_raw = combined.group(2).strip().capitalize()
        gender = "Male" if g_raw.startswith("M") else "Female"
        return age, gender

    # 2. Separate age patterns
    age_match = re.search(r"\b(?:Age|Age\s*Years?)\s*[:=]?\s*(\d{1,3})\b", text, re.IGNORECASE)
    if not age_match:
        age_match = re.search(r"\b(\d{1,3})\s*(?:Y(?:ears?|rs?)|yrs?\.?)\b", text, re.IGNORECASE)
    if age_match:
        try:
            val = int(age_match.group(1))
            if 0 <= val <= 130:
                age = val
        except ValueError:
            pass

    # 3. Separate gender/sex patterns
    gender_match = re.search(r"\b(?:Gender|Sex)\s*[:=]?\s*(Male|Female|M|F)\b", text, re.IGNORECASE)
    if gender_match:
        g_raw = gender_match.group(1).strip().capitalize()
        gender = "Male" if g_raw.startswith("M") else "Female"

    return age, gender


def detect_header_boundary(page: pymupdf.Page) -> SanitizedPatientContext:
    """Analyze page geometry to detect header boundary and extract sanitized context.

    Identifies table header keywords to isolate the header area.
    """
    text = page.get_text()
    age, gender = extract_patient_context_from_text(text)

    # Search for table header row to determine vertical cutoff
    blocks = page.get_text("blocks")
    header_cutoff_y = 0.0

    table_header_keywords = re.compile(
        r"\b(test|parameter|investigation|analyte|observed\s+value|result|reference\s+interval|biological\s+reference)\b",
        re.IGNORECASE,
    )

    for b in blocks:
        # b: (x0, y0, x1, y1, "text", block_no, block_type)
        if len(b) >= 5:
            b_text = str(b[4])
            if table_header_keywords.search(b_text):
                header_cutoff_y = b[1]  # Top y of table header block
                break

    # Default fallback: top 25% of page if no header keyword detected
    if header_cutoff_y <= 0:
        header_cutoff_y = page.rect.height * 0.25

    return SanitizedPatientContext(
        age=age,
        gender=gender,
        header_boundary_y=header_cutoff_y,
    )
