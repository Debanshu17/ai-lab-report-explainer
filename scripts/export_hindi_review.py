"""Export side-by-side English vs Hindi review packet to docs/hindi_review_packet.md.

Directly supports closing Open Item #3 in docs/KB_OPEN_ITEMS.md:
'All Hindi text is unreviewed (hindi_reviewed=false); a native Hindi speaker must review it.'
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Fix Windows console encoding
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from src.data.loaders import load_knowledge_base
from src.explain.hindi import load_hindi_glossary


def generate_hindi_review_packet(
    output_path: Path = Path("docs/hindi_review_packet.md"),
) -> str:
    """Generate Markdown review packet with side-by-side English vs Hindi text."""
    kb = load_knowledge_base()
    glossary = load_hindi_glossary()

    lines: list[str] = [
        "# Knowledge Base Hindi Review Packet (docs/hindi_review_packet.md)",
        "",
        "> **PURPOSE**: This document provides a side-by-side English vs. Hindi comparison of all 20 curated blood tests and 5 general educational topics. It is designed for a native Hindi speaker with clinical/medical literacy to review, edit, and approve prior to production deployment (tracking **Open Item #3** in `docs/KB_OPEN_ITEMS.md`).",
        "",
        "## Reviewer Guidelines",
        "1. **Number Rule:** Numbers MUST remain Western Arabic digits (`12.4`, not `१२.४`).",
        "2. **Unit Rule:** Scientific units MUST remain standard Latin symbols (`g/dL`, `mg/dL`, `cells/µL`).",
        "3. **Tone Rule:** The language must remain strictly educational, non-alarmist, and non-prescriptive (no diagnosis, medicine names, or false reassurance).",
        "",
        "---",
        "",
        "## Part 1: Curated Blood Tests (20 Tests)",
        "",
    ]

    for i, test in enumerate(kb.blood_tests, 1):
        lines.extend([
            f"### {i}. {test.test_name} (`{test.test_id}`)",
            f"- **Category:** {test.category}",
            f"- **Standard Unit:** `{test.standard_unit}`",
            f"- **English Name:** {test.test_name}",
            f"- **Hindi Name (Devanagari):** **{test.test_name_hindi}**",
            f"- **Transliteration:** *{test.test_name_transliteration}*",
            "",
            "| Section | English Text | Hindi Translation (Unreviewed) |",
            "|---|---|---|",
            f"| **Clinical Summary** | {test.clinical_summary} | {test.hindi_summary} |",
            f"| **Context (Low)** | {test.general_context_low} | *(Generated dynamically using template)* |",
            f"| **Context (High)** | {test.general_context_high} | *(Generated dynamically using template)* |",
            "",
            "**Review Checklist:**",
            "- [ ] Translation is accurate and natural Hindi",
            "- [ ] Devanagari spelling of medical terms is correct",
            "- [ ] Non-diagnostic educational boundary is maintained",
            "- [ ] Numerals and scientific units remain untranslated",
            "",
            "**Reviewer Notes / Corrections:**",
            "> ",
            "",
            "---",
            "",
        ])

    lines.extend([
        "## Part 2: General Educational Topics (5 Topics)",
        "",
    ])

    topic_hindi_map = glossary.get("general_topics", {})

    for j, topic in enumerate(kb.general_topics, 1):
        top_info = topic_hindi_map.get(topic.topic_id, {})
        hi_title = top_info.get("title_hi", topic.title)

        lines.extend([
            f"### {j}. {topic.title} (`{topic.topic_id}`)",
            f"- **English Title:** {topic.title}",
            f"- **Hindi Title:** **{hi_title}**",
            f"- **Sources Attached:** {len(topic.sources)}",
            "",
            f"**English Summary:**\n{topic.summary}",
            "",
            "**Review Checklist:**",
            "- [ ] Topic title in Hindi is clear and accurate",
            "- [ ] Educational intent is preserved without medical prescription",
            "",
            "**Reviewer Notes / Corrections:**",
            "> ",
            "",
            "---",
            "",
        ])

    lines.extend([
        "## Part 3: Reviewer Sign-Off",
        "",
        "| Field | Reviewer Submission |",
        "|---|---|",
        "| **Reviewer Full Name** | ___________________________________ |",
        "| **Qualifications / Fluency** | ___________________________________ |",
        "| **Review Completion Date** | ___________________________________ |",
        "| **Overall Recommendation** | `[ ] APPROVED` &nbsp;&nbsp;&nbsp; `[ ] APPROVED WITH EDITS` &nbsp;&nbsp;&nbsp; `[ ] REJECTED` |",
        "",
    ])

    content = "\n".join(lines)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, mode="w", encoding="utf-8") as f:
        f.write(content)

    return content


if __name__ == "__main__":
    generate_hindi_review_packet()
    print("Successfully exported docs/hindi_review_packet.md")
