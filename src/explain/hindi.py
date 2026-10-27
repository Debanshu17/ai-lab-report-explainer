"""Hindi localization helpers, glossary loader, and Devanagari validation rules.

Enforces:
1. Devanagari Hindi text for explanations while preserving Western digits (12.4, not १२.४).
2. Latin symbols for laboratory units (e.g. g/dL, mg/dL, cells/µL, µIU/mL).
3. Number and unit invariance check between English and Hindi outputs.
4. Surface Open Item #3 in-app review notice (hindi_reviewed=false).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional, Sequence

GLOSSARY_PATH = Path("data/glossary/hindi_glossary.json")

# Devanagari digit characters ० - ९
DEVANAGARI_DIGITS_REGEX = re.compile(r"[\u0966-\u096F]")

HINDI_FLAG_LABELS = {
    "NORMAL": "सामान्य (मुद्रित सीमा के भीतर)",
    "LOW": "निम्न (मुद्रित सीमा से नीचे)",
    "HIGH": "उच्च (मुद्रित सीमा से ऊपर)",
    "NEEDS_REVIEW": "समीक्षा आवश्यक",
}

HINDI_UNREVIEWED_NOTICE = (
    "सूचना: इस रिपोर्ट का हिंदी अनुवाद प्रारंभिक है और एक मूल हिंदी भाषी चिकित्सा विशेषज्ञ द्वारा "
    "समीक्षाधीन है (hindi_reviewed=false)।"
)

_GLOSSARY_CACHE: Optional[dict] = None


def load_hindi_glossary(glossary_path: Optional[Path] = None) -> dict:
    """Load or return cached Hindi terminology glossary."""
    global _GLOSSARY_CACHE
    target_path = glossary_path or GLOSSARY_PATH
    if _GLOSSARY_CACHE is not None and target_path == GLOSSARY_PATH:
        return _GLOSSARY_CACHE

    if not target_path.exists():
        from scripts.build_hindi_glossary import build_hindi_glossary
        _GLOSSARY_CACHE = build_hindi_glossary(output_path=target_path)
    else:
        with open(target_path, mode="r", encoding="utf-8") as f:
            _GLOSSARY_CACHE = json.load(f)

    return _GLOSSARY_CACHE


def format_hindi_value_meaning(
    test_name_hindi: str,
    value: Optional[float],
    unit: str,
    ref_range: str,
    flag: str,
    hindi_summary: str,
) -> str:
    """Construct an educational explanation in Hindi adhering to safety and formatting principles.
    
    Guarantees that numbers remain Western digits and units remain Latin.
    """
    val_str = str(value) if value is not None else "अज्ञात"
    flag_upper = flag.strip().upper()

    if flag_upper == "NORMAL":
        return (
            f"आपका परिणाम {val_str} {unit} रिपोर्ट पर मुद्रित संदर्भ सीमा ({ref_range}) के भीतर है। "
            f"शैक्षणिक संदर्भ में, परीक्षण के समय यह स्तर रिपोर्टिंग प्रयोगशाला के सामान्य दायरे में पाया गया। "
            f"{test_name_hindi} के बारे में: {hindi_summary}"
        )
    elif flag_upper == "LOW":
        return (
            f"आपका परिणाम {val_str} {unit} रिपोर्ट पर मुद्रित संदर्भ सीमा ({ref_range}) से नीचे है। "
            f"शैक्षणिक संदर्भ: {hindi_summary} "
            f"यह ध्यान रखना आवश्यक है कि केवल आपके डॉक्टर ही आपकी व्यक्तिगत स्वास्थ्य स्थिति के आधार पर "
            f"इस परिणाम की सही व्याख्या कर सकते हैं।"
        )
    elif flag_upper == "HIGH":
        return (
            f"आपका परिणाम {val_str} {unit} रिपोर्ट पर मुद्रित संदर्भ सीमा ({ref_range}) से ऊपर है। "
            f"शैक्षणिक संदर्भ: {hindi_summary} "
            f"यह ध्यान रखना आवश्यक है कि केवल आपके डॉक्टर ही आपकी व्यक्तिगत स्वास्थ्य स्थिति के आधार पर "
            f"इस परिणाम की सही व्याख्या कर सकते हैं।"
        )
    else:
        return (
            f"परीक्षण {test_name_hindi} का परिणाम {val_str} {unit} और संदर्भ सीमा ({ref_range}) "
            f"अस्पष्ट या जटिल है। सटीक व्याख्या के लिए अपने चिकित्सक से परामर्श लें।"
        )


def verify_number_and_unit_invariance(
    hindi_text: str,
    expected_values: Sequence[float],
    expected_units: Sequence[str],
) -> tuple[bool, list[str]]:
    """Validate that Hindi text preserves Western digits and exact Latin scientific units.

    Enforces:
    1. Zero Devanagari numerals (०, १, २, etc.) to prevent clinical misinterpretation.
    2. Exact presence of all expected numeric float values as Western digits.
    3. Exact presence of Latin scientific units.

    Returns:
        tuple[bool, list[str]]: (is_valid, violation_reasons).
    """
    violations: list[str] = []

    # 1. Check for Devanagari numerals
    dev_matches = DEVANAGARI_DIGITS_REGEX.findall(hindi_text)
    if dev_matches:
        violations.append(
            f"Found forbidden Devanagari numeral(s): {set(dev_matches)}. All numbers must use Western digits."
        )

    # 2. Check for presence of expected numeric values
    for val in expected_values:
        val_str = str(val)
        val_str_alt = f"{val:.1f}"
        val_int_str = str(int(val)) if val == int(val) else None

        has_match = (val_str in hindi_text) or (val_str_alt in hindi_text)
        if not has_match and val_int_str:
            has_match = val_int_str in hindi_text

        if not has_match:
            violations.append(f"Expected numeric value '{val}' missing from Hindi explanation.")

    # 3. Check for expected Latin units
    for u in expected_units:
        clean_unit = u.strip()
        if clean_unit and clean_unit not in hindi_text:
            violations.append(f"Expected scientific unit '{clean_unit}' missing or corrupted in Hindi explanation.")

    is_valid = len(violations) == 0
    return is_valid, violations
