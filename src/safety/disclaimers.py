"""Code-injected disclaimers and emergency urgent-care notifications.

Enforces Core Principle #3:
- Always inject an unequivocal educational disclaimer at the top of the report.
- Inject a bold urgent-care warning footer if any test exhibits critical bounds
  or if the clinical context suggests urgent symptoms.
"""

from __future__ import annotations

from typing import Optional

EDUCATIONAL_DISCLAIMER_EN = (
    "IMPORTANT EDUCATIONAL NOTICE: This application is strictly an educational tool and does NOT provide "
    "medical advice, clinical diagnosis, treatment recommendations, or prescriptions. Laboratory reference "
    "intervals vary across different testing facilities and methodologies. A single test result cannot be "
    "interpreted in isolation. Always consult a qualified physician or healthcare provider for any medical "
    "interpretation, diagnosis, or health concerns."
)

EDUCATIONAL_DISCLAIMER_HI = (
    "महत्वपूर्ण शैक्षणिक सूचना: यह एप्लिकेशन पूरी तरह से एक शैक्षणिक साधन है और यह चिकित्सीय सलाह, "
    "रोग निदान, उपचार सिफारिशें या दवा के नुस्खे प्रदान नहीं करता है। विभिन्न प्रयोगशालाओं और परीक्षण "
    "विधियों में संदर्भ सीमाएं भिन्न हो सकती हैं। किसी एक परीक्षण परिणाम की अलग से व्याख्या नहीं की जा सकती। "
    "किसी भी चिकित्सीय व्याख्या, निदान या स्वास्थ्य संबंधी चिंताओं के लिए हमेशा एक योग्य चिकित्सक से परामर्श लें।"
)

URGENT_CARE_FOOTER_EN = (
    "EMERGENCY MEDICAL NOTICE: If you are experiencing sudden, severe, or concerning symptoms—such as "
    "chest pain, difficulty breathing, sudden severe headache, sudden weakness or numbness, severe abdominal pain, "
    "high fever with stiff neck, or loss of consciousness—do not wait for laboratory report interpretations. "
    "Seek emergency medical evaluation immediately by calling emergency services (such as 911 or 112) or "
    "going to the nearest hospital emergency room."
)

URGENT_CARE_FOOTER_HI = (
    "आपातकालीन चिकित्सा सूचना: यदि आप अचानक, गंभीर या चिंताजनक लक्षणों का अनुभव कर रहे हैं—जैसे कि सीने में दर्द, "
    "सांस लेने में कठिनाई, अचानक तेज सिरदर्द, अचानक कमजोरी या सुन्नता, पेट में तेज दर्द, गर्दन में अकड़न के साथ तेज बुखार, "
    "या बेहोशी—तो लैब रिपोर्ट की व्याख्या का इंतजार न करें। तुरंत आपातकालीन चिकित्सा सहायता लें या निकटतम अस्पताल "
    "के आपातकालीन विभाग (इमरजेंसी) में जाएं।"
)


def get_disclaimer(language: str = "en") -> str:
    """Return language-specific educational disclaimer."""
    return EDUCATIONAL_DISCLAIMER_HI if language.strip().lower() == "hi" else EDUCATIONAL_DISCLAIMER_EN


def get_urgent_care_footer(language: str = "en") -> str:
    """Return language-specific emergency care notice."""
    return URGENT_CARE_FOOTER_HI if language.strip().lower() == "hi" else URGENT_CARE_FOOTER_EN


def requires_urgent_care_footer(
    flags: list[str],
    has_critical_bounds: bool = False,
) -> bool:
    """Determine whether a report explanation must display the urgent care footer.

    Args:
        flags: List of test flags (e.g. ['NORMAL', 'HIGH', 'CRITICAL', 'LOW'])
        has_critical_bounds: Flag indicating extreme clinical deviation.

    Returns:
        bool: True if emergency care notice is required.
    """
    if has_critical_bounds:
        return True
    return any(f.strip().upper() == "CRITICAL" for f in flags)
