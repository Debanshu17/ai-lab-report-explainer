"""Hindi localization helpers and educational phrasing templates.

Preserves English numerals and scientific units (e.g. mg/dL, g/dL, cells/µL) to ensure
clinical precision. Surfaces the tracked open item regarding unreviewed Hindi text.
"""

from __future__ import annotations

from typing import Optional

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


def format_hindi_value_meaning(
    test_name_hindi: str,
    value: Optional[float],
    unit: str,
    ref_range: str,
    flag: str,
    hindi_summary: str,
) -> str:
    """Construct an educational explanation in Hindi adhering to safety principles."""
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
