"""Generate data/glossary/hindi_glossary.json from Knowledge Base."""

from __future__ import annotations

import json
from pathlib import Path

CATEGORY_HINDI_MAP = {
    "Complete Blood Count": "पूर्ण रक्त गणना (सीबीसी)",
    "Metabolic": "चयापचय (मेटाबॉलिक)",
    "Lipid Profile": "लिपिड प्रोफाइल (रक्त वसा)",
    "Kidney Function": "वृक्क कार्यप्रणाली (किडनी फंक्शन)",
    "Liver Function": "यकृत कार्यप्रणाली (लिवर फंक्शन)",
    "Thyroid": "थायरॉयड परीक्षण",
    "Vitamins": "विटामिन स्तर",
}

DIRECTION_HINDI_MAP = {
    "NORMAL": "सामान्य (मुद्रित सीमा के भीतर)",
    "LOW": "निम्न (मुद्रित सीमा से नीचे)",
    "HIGH": "उच्च (मुद्रित सीमा से ऊपर)",
    "NEEDS_REVIEW": "समीक्षा आवश्यक",
}

TOPIC_HINDI_MAP = {
    "WHY_RANGES_DIFFER": "प्रयोगशाला संदर्भ सीमाएं क्यों भिन्न होती हैं?",
    "OUT_OF_RANGE_MEANING": "संदर्भ सीमा से बाहर परिणाम का क्या अर्थ है?",
    "FASTING_BEFORE_TEST": "रक्त परीक्षण से पहले उपवास (फास्टिंग)",
    "URGENT_MEDICAL_CARE": "आपातकालीन चिकित्सा देखभाल कब लें?",
    "PROFESSIONAL_INTERPRETATION": "चिकित्सक द्वारा रिपोर्ट की व्याख्या क्यों आवश्यक है?",
}


def build_hindi_glossary(
    kb_path: Path = Path("data/inputs/ai_lab_report_knowledge_base_final.json"),
    output_path: Path = Path("data/glossary/hindi_glossary.json"),
) -> dict:
    """Build and write the canonical Hindi glossary."""
    with open(kb_path, mode="r", encoding="utf-8") as f:
        kb = json.load(f)

    glossary = {
        "metadata": {
            "title": "AI Lab Report Explainer - Hindi Terminology Glossary",
            "version": "1.0",
            "source": "Curated Knowledge Base (ai_lab_report_knowledge_base_final.json)",
            "number_rule": "Numbers MUST stay Western Arabic digits (e.g. 12.4, not १२.४).",
            "unit_rule": "Units MUST stay standard Latin symbols (e.g. g/dL, mg/dL, cells/µL).",
            "status": "Unreviewed by native clinical Hindi speaker (pending human review).",
        },
        "tests": {},
        "categories": CATEGORY_HINDI_MAP,
        "directions": DIRECTION_HINDI_MAP,
        "general_topics": {},
        "disclaimers": {
            "educational_disclaimer": (
                "महत्वपूर्ण शैक्षणिक सूचना: यह एप्लिकेशन पूरी तरह से एक शैक्षणिक साधन है और यह चिकित्सीय सलाह, "
                "रोग निदान, उपचार सिफारिशें या दवा के नुस्खे प्रदान नहीं करता है।"
            ),
            "urgent_care_footer": (
                "आपातकालीन चिकित्सा सूचना: यदि आप अचानक या गंभीर लक्षणों का अनुभव कर रहे हैं, तो तुरंत "
                "आपातकालीन चिकित्सा सहायता (112 या निकटतम आपातकालीन कक्ष) लें।"
            ),
            "unreviewed_notice": (
                "सूचना: इस रिपोर्ट का हिंदी अनुवाद प्रारंभिक है और एक मूल हिंदी भाषी चिकित्सा विशेषज्ञ द्वारा "
                "समीक्षाधीन है (hindi_reviewed=false)।"
            ),
        },
    }

    for test in kb["blood_tests"]:
        tid = test["test_id"]
        cat = test["category"]
        glossary["tests"][tid] = {
            "test_id": tid,
            "test_name_en": test["test_name"],
            "test_name_hi": test["test_name_hindi"],
            "test_name_transliteration": test["test_name_transliteration"],
            "category_en": cat,
            "category_hi": CATEGORY_HINDI_MAP.get(cat, cat),
            "standard_unit": test["standard_unit"],
            "aliases": test["aliases"],
        }

    for topic in kb["general_topics"]:
        top_id = topic["topic_id"]
        glossary["general_topics"][top_id] = {
            "topic_id": top_id,
            "title_en": topic["title"],
            "title_hi": TOPIC_HINDI_MAP.get(top_id, topic["title"]),
        }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, mode="w", encoding="utf-8") as out_f:
        json.dump(glossary, out_f, indent=2, ensure_ascii=False)

    return glossary


if __name__ == "__main__":
    glossary = build_hindi_glossary()
    print(f"Successfully generated Hindi glossary with {len(glossary['tests'])} tests and {len(glossary['categories'])} categories.")
