"""Number, range, and unit formatting utilities for synthetic reports."""

from __future__ import annotations

import re
from typing import Optional, Tuple


def format_indian_number(n: float | int) -> str:
    """Format an integer or float with Indian digit grouping (e.g. 1,50,000)."""
    if isinstance(n, float):
        if n.is_integer():
            int_part = int(n)
            dec_part = ""
        else:
            s = f"{n:.2f}".rstrip("0").rstrip(".")
            parts = s.split(".")
            int_part = int(parts[0])
            dec_part = "." + parts[1] if len(parts) > 1 else ""
    else:
        int_part = n
        dec_part = ""

    s_int = str(abs(int_part))
    if len(s_int) <= 3:
        formatted = s_int
    else:
        last3 = s_int[-3:]
        rest = s_int[:-3]
        groups = []
        while len(rest) > 2:
            groups.insert(0, rest[-2:])
            rest = rest[:-2]
        if rest:
            groups.insert(0, rest)
        formatted = ",".join(groups) + "," + last3

    if int_part < 0:
        formatted = "-" + formatted
    return formatted + dec_part


def format_western_number(n: float | int) -> str:
    """Format an integer or float with Western standard digit grouping (e.g. 150,000)."""
    if isinstance(n, float):
        if n.is_integer():
            return f"{int(n):,}"
        formatted = f"{n:,.2f}".rstrip("0").rstrip(".")
        return formatted
    return f"{n:,}"


def compute_expected_flag(
    value: Optional[float],
    value_text: str,
    range_text: str,
    patient_sex: Optional[str] = None,
) -> Tuple[str, str, Optional[float], Optional[float]]:
    """Compute expected ground-truth flag strictly against the printed range.

    Enforces inclusive boundaries (value == limit is NORMAL).
    Multi-tier or unparseable ranges return NEEDS_REVIEW.

    Returns:
        (expected_flag, range_type, ref_low, ref_high)
        expected_flag: 'LOW', 'HIGH', 'NORMAL', or 'NEEDS_REVIEW'
        range_type: 'between', 'upper', 'lower', 'qualitative', 'multi_tier', 'sex_specific', 'unparseable'
    """
    clean_range = range_text.strip()

    # 1. Multi-tier check
    if any(tier in clean_range.lower() for tier in ["desirable", "borderline", "optimal", "near optimal"]):
        return "NEEDS_REVIEW", "multi_tier", None, None

    # 2. Qualitative check
    qual_normals = {"negative", "nil", "non-reactive", "absent", "normal"}
    val_clean = value_text.strip().lower()
    if any(q in clean_range.lower() for q in ["negative", "nil", "non-reactive", "absent"]):
        range_type = "qualitative"
        if val_clean in qual_normals:
            return "NORMAL", range_type, None, None
        else:
            return "HIGH", range_type, None, None

    # 3. Sex-specific single-cell check, e.g. "M: 13.8-17.2 F: 12.1-15.1" or "Male: 13.8-17.2, Female: 12.1-15.1"
    if ("m:" in clean_range.lower() or "male:" in clean_range.lower()) and ("f:" in clean_range.lower() or "female:" in clean_range.lower()):
        if not patient_sex:
            return "NEEDS_REVIEW", "sex_specific", None, None
        
        sex_lower = patient_sex.strip().lower()
        # Extract the appropriate sex range
        m_match = re.search(r"(?:M|Male):\s*([0-9.]+)\s*-\s*([0-9.]+)", clean_range, re.IGNORECASE)
        f_match = re.search(r"(?:F|Female):\s*([0-9.]+)\s*-\s*([0-9.]+)", clean_range, re.IGNORECASE)
        
        if sex_lower == "male" and m_match:
            low, high = float(m_match.group(1)), float(m_match.group(2))
        elif sex_lower == "female" and f_match:
            low, high = float(f_match.group(1)), float(f_match.group(2))
        else:
            return "NEEDS_REVIEW", "sex_specific", None, None

        if value is None:
            return "NEEDS_REVIEW", "sex_specific", low, high

        if value < low:
            return "LOW", "sex_specific", low, high
        elif value > high:
            return "HIGH", "sex_specific", low, high
        else:
            return "NORMAL", "sex_specific", low, high

    # If no numeric value available
    if value is None:
        return "NEEDS_REVIEW", "unparseable", None, None

    # 4. Upper bound one-sided: "< 200", "<= 100", "Up to 5.0", "< 5.7"
    upper_match = re.match(r"^(?:<|<=|up\s+to|less\s+than)\s*([0-9.]+)$", clean_range, re.IGNORECASE)
    if upper_match:
        high = float(upper_match.group(1))
        flag = "NORMAL" if value <= high else "HIGH"
        return flag, "upper", None, high

    # 5. Lower bound one-sided: "> 40", ">= 50", "Greater than 40"
    lower_match = re.match(r"^(?:>|>=|greater\s+than)\s*([0-9.]+)$", clean_range, re.IGNORECASE)
    if lower_match:
        low = float(lower_match.group(1))
        flag = "NORMAL" if value >= low else "LOW"
        return flag, "lower", low, None

    # 6. Standard between: "13.0 - 17.0", "13-17", "13.0 to 17.0"
    between_match = re.match(r"^([0-9.]+)\s*(?:-|to)\s*([0-9.]+)$", clean_range)
    if between_match:
        low = float(between_match.group(1))
        high = float(between_match.group(2))
        if value < low:
            flag = "LOW"
        elif value > high:
            flag = "HIGH"
        else:
            flag = "NORMAL"
        return flag, "between", low, high

    return "NEEDS_REVIEW", "unparseable", None, None
