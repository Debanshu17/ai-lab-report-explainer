"""Normalization engine for extracted numbers, units, and test aliases.

Handles:
- Western and Indian comma formats (1,234.5 vs 1,50,000)
- Trailing flag markers (e.g. '14.8 H' -> value=14.8, marker='H')
- Unit standardization (u/µ, cumm, mg/dL)
- Alias -> canonical test_id resolution with confidence tracking
"""

from __future__ import annotations

import difflib
import re
from typing import Optional, Tuple
from pydantic import BaseModel, Field

from src.config import settings
from src.data.mapping import AliasResolver, normalize_alias


class NormalizedTestRow(BaseModel):
    """Cleaned and normalized test row ready for deterministic flagging."""

    raw_test_name: str
    canonical_test_id: Optional[str] = None
    confidence: float = 1.0  # 1.0 for exact alias match, <1.0 for fuzzy
    is_fuzzy_match: bool = False

    raw_value_text: str
    numeric_value: Optional[float] = None
    is_qualitative: bool = False
    flag_marker: Optional[str] = None  # e.g. 'H' or 'L' if printed

    raw_unit: str
    normalized_unit: str

    raw_range_text: str
    normalized_range_text: str

    page: int
    section: Optional[str] = None
    is_unparsed: bool = False


def normalize_numeric_value(val_str: str) -> Tuple[Optional[float], Optional[str], bool]:
    """Parse number string handling commas (Western & Indian) and trailing H/L flags.

    Returns:
        (numeric_val, flag_marker, is_qualitative)
    """
    if not val_str:
        return None, None, False

    clean = val_str.strip()

    # Check qualitative results
    qual_keywords = {"negative", "nil", "non-reactive", "absent", "normal", "positive", "reactive"}
    if clean.lower() in qual_keywords:
        return None, None, True

    # Detect trailing H or L flag marker: e.g. "14.8 H", "14.8H", "3.2 L"
    flag_marker: Optional[str] = None
    flag_match = re.search(r"^(.*?)\s*([HL])$", clean)
    if flag_match:
        clean = flag_match.group(1).strip()
        flag_marker = flag_match.group(2)

    # Strip grouping commas
    clean_no_commas = clean.replace(",", "").strip()

    # Attempt float conversion
    try:
        num = float(clean_no_commas)
        return num, flag_marker, False
    except ValueError:
        return None, flag_marker, False


def normalize_unit_string(unit_str: str) -> str:
    """Normalize common lab unit variations."""
    if not unit_str:
        return ""

    u = unit_str.strip()

    # Normalize micro sign variations: \u03bc (Greek mu), 'u', 'mcg'
    # Replace 'cells/uL' or 'cells/mcL' with 'cells/µL'
    u = re.sub(r"(?i)\bcells\s*/\s*(?:uL|mcL|L)\b", "cells/µL", u)
    u = u.replace("\u03bc", "\u00b5")  # Greek mu -> micro sign

    # Replace 'cumm' with 'cells/µL'
    if re.search(r"(?i)\bcumm\b", u):
        u = "cells/µL"

    # Case normalizations
    unit_map = {
        "g/dl": "g/dL",
        "mg/dl": "mg/dL",
        "fl": "fL",
        "miu/l": "mIU/L",
        "ng/ml": "ng/mL",
        "pg/ml": "pg/mL",
        "u/l": "U/L",
        "mmol/l": "mmol/L",
        "g/l": "g/L",
        "%": "%",
        "cells/L": "cells/µL",
        "million cells/L": "million cells/µL",
        "million cells/ul": "million cells/µL",
    }
    lowered = u.lower()
    for k, v in unit_map.items():
        if lowered == k.lower():
            return v

    return u


def resolve_alias_with_confidence(
    test_name: str,
    resolver: AliasResolver,
    fuzzy_threshold: float = settings.ALIAS_FUZZY_THRESHOLD,
) -> Tuple[Optional[str], float, bool]:
    """Resolve raw test name to canonical test_id with fuzzy fallback.

    Returns:
        (canonical_test_id, confidence, is_fuzzy)
    """
    if not test_name:
        return None, 0.0, False

    # 1. Exact deterministic normalized resolution
    exact_id = resolver.resolve(test_name)
    if exact_id:
        return exact_id, 1.0, False

    # 2. Fuzzy fallback across known normalized alias keys
    norm_name = normalize_alias(test_name)
    best_id: Optional[str] = None
    best_score = 0.0

    for alias_key, tid in resolver._alias_to_test_id.items():
        score = difflib.SequenceMatcher(None, norm_name, alias_key).ratio() * 100.0
        if score > best_score:
            best_score = score
            best_id = tid

    if best_score >= fuzzy_threshold and best_id:
        return best_id, round(best_score / 100.0, 2), True

    return None, 0.0, False


def normalize_raw_row(
    raw_name: str,
    raw_val_str: str,
    raw_unit_str: str,
    raw_range_str: str,
    page: int = 1,
    section: Optional[str] = None,
    resolver: Optional[AliasResolver] = None,
) -> NormalizedTestRow:
    """Transform raw extracted tokens into a NormalizedTestRow."""
    res = resolver or AliasResolver()

    # Normalize name and resolve test_id
    clean_name = re.sub(r"\s+", " ", raw_name).strip()
    tid, conf, is_fuzzy = resolve_alias_with_confidence(clean_name, res)

    # Normalize value and flag marker
    val_num, flag_marker, is_qual = normalize_numeric_value(raw_val_str)

    # Normalize unit
    norm_unit = normalize_unit_string(raw_unit_str)

    # Clean range string (normalize dashes and spacing)
    clean_range = re.sub(r"[–—−]", "-", raw_range_str)  # Unicode dashes to standard hyphen
    clean_range = re.sub(r"\s+", " ", clean_range).strip()

    # Row is considered unparsed if neither a numeric value nor a qualitative value was captured
    is_unparsed = (val_num is None and not is_qual) or not clean_range

    return NormalizedTestRow(
        raw_test_name=clean_name,
        canonical_test_id=tid,
        confidence=conf,
        is_fuzzy_match=is_fuzzy,
        raw_value_text=raw_val_str.strip(),
        numeric_value=val_num,
        is_qualitative=is_qual,
        flag_marker=flag_marker,
        raw_unit=raw_unit_str.strip(),
        normalized_unit=norm_unit,
        raw_range_text=raw_range_str.strip(),
        normalized_range_text=clean_range,
        page=page,
        section=section,
        is_unparsed=is_unparsed,
    )
