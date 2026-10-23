"""Pure Python reference range parser.

Parses diverse clinical reference interval formats:
- Between: '13.0 - 17.0', '13-17', '13.0 to 17.0'
- Upper: '< 200', '<= 1.2', 'Up to 5.0', 'Less than 100'
- Lower: '> 40', '>= 50', 'Greater than 40'
- Qualitative: 'Negative', 'Non-reactive', 'Nil', 'Absent'
- Multi-tier: 'Desirable <200, Borderline 200-239, High >=240'
- Sex-specific in single cell: 'M: 13.8-17.2 F: 12.1-15.1'

Handles Unicode dashes (–, —, −) and inequality signs (≤, ≥).
"""

from __future__ import annotations

import re
from typing import Optional, Set, Tuple
from pydantic import BaseModel, Field


class ParsedRange(BaseModel):
    """Structured representation of a parsed laboratory reference range."""

    range_type: str  # between, upper, lower, qualitative, multi_tier, sex_specific, unparseable
    low: Optional[float] = None
    high: Optional[float] = None
    qualitative_normal_set: Optional[Set[str]] = None
    male_range: Optional[Tuple[float, float]] = None
    female_range: Optional[Tuple[float, float]] = None
    raw_text: str
    is_valid: bool = True
    requires_sex: bool = False


def normalize_range_symbols(text: str) -> str:
    """Normalize Unicode dashes, quotes, and comparison signs."""
    if not text:
        return ""
    # Unicode dashes to standard hyphen
    clean = re.sub(r"[–—−]", "-", text)
    # Unicode inequalities
    clean = clean.replace("≤", "<=").replace("≥", ">=")
    # Collapse whitespace
    return re.sub(r"\s+", " ", clean).strip()


def parse_reference_range(range_text: str) -> ParsedRange:
    """Parse a reference range string into a structured ParsedRange object."""
    if not range_text or not range_text.strip():
        return ParsedRange(range_type="unparseable", raw_text="", is_valid=False)

    clean = normalize_range_symbols(range_text)

    # 1. Multi-tier range detection (>=2 labelled tiers or lipid classifications)
    multi_tier_keywords = ["desirable", "borderline", "optimal", "near optimal", "high risk", "moderate risk"]
    if any(k in clean.lower() for k in multi_tier_keywords):
        return ParsedRange(
            range_type="multi_tier",
            raw_text=clean,
            is_valid=True,
        )

    # Multiple tier indicator check, e.g. "<200, 200-239, >=240"
    tier_splits = [t.strip() for t in clean.split(",") if t.strip()]
    if len(tier_splits) >= 2 and any("<" in t or ">" in t or "-" in t for t in tier_splits):
        # If it contains multiple distinct ranges or inequalities
        if sum(1 for t in tier_splits if any(c in t for c in ["<", ">", "-", "to"])) >= 2:
            return ParsedRange(
                range_type="multi_tier",
                raw_text=clean,
                is_valid=True,
            )

    # 2. Qualitative range detection
    qual_normals = {"negative", "nil", "non-reactive", "absent", "normal"}
    clean_lower = clean.lower()
    if clean_lower in qual_normals or any(q in clean_lower for q in ["non-reactive", "negative", "nil", "absent"]):
        return ParsedRange(
            range_type="qualitative",
            qualitative_normal_set=qual_normals,
            raw_text=clean,
            is_valid=True,
        )

    # 3. Sex-specific single-cell format: "M: 13.8-17.2 F: 12.1-15.1" or "Male: 13.8-17.2, Female: 12.1-15.1"
    is_m = bool(re.search(r"\b(?:M|Male)\s*:\s*[0-9.]+\s*-\s*[0-9.]+", clean, re.IGNORECASE))
    is_f = bool(re.search(r"\b(?:F|Female)\s*:\s*[0-9.]+\s*-\s*[0-9.]+", clean, re.IGNORECASE))
    if is_m and is_f:
        m_match = re.search(r"(?:M|Male)\s*:\s*([0-9.]+)\s*-\s*([0-9.]+)", clean, re.IGNORECASE)
        f_match = re.search(r"(?:F|Female)\s*:\s*([0-9.]+)\s*-\s*([0-9.]+)", clean, re.IGNORECASE)
        m_range = (float(m_match.group(1)), float(m_match.group(2))) if m_match else None
        f_range = (float(f_match.group(1)), float(f_match.group(2))) if f_match else None
        return ParsedRange(
            range_type="sex_specific",
            male_range=m_range,
            female_range=f_range,
            raw_text=clean,
            is_valid=True,
            requires_sex=True,
        )

    # 4. Upper bound one-sided: "< 200", "<= 100", "Up to 5.0", "Less than 100", "Below 200"
    upper_match = re.match(r"^(?:<=|<|up\s+to|less\s+than|below)\s*([0-9.]+)$", clean, re.IGNORECASE)
    if upper_match:
        high_val = float(upper_match.group(1))
        return ParsedRange(
            range_type="upper",
            high=high_val,
            raw_text=clean,
            is_valid=True,
        )

    # 5. Lower bound one-sided: "> 40", ">= 50", "Greater than 40", "Above 40"
    lower_match = re.match(r"^(?:>=|>|greater\s+than|above|more\s+than)\s*([0-9.]+)$", clean, re.IGNORECASE)
    if lower_match:
        low_val = float(lower_match.group(1))
        return ParsedRange(
            range_type="lower",
            low=low_val,
            raw_text=clean,
            is_valid=True,
        )

    # 6. Standard between format: "13.0 - 17.0", "13-17", "13.0 to 17.0"
    between_match = re.match(r"^([0-9.]+)\s*(?:-|to)\s*([0-9.]+)$", clean, re.IGNORECASE)
    if between_match:
        low_val = float(between_match.group(1))
        high_val = float(between_match.group(2))
        return ParsedRange(
            range_type="between",
            low=low_val,
            high=high_val,
            raw_text=clean,
            is_valid=True,
        )

    # Unparseable fallback
    return ParsedRange(
        range_type="unparseable",
        raw_text=clean,
        is_valid=False,
    )
