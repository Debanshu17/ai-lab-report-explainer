"""Verified LLM fallback for lab test rows that rule-based extraction cannot parse.

Enforces:
- Strict Pydantic JSON schema.
- Verbatim source text verification: extracted value and range MUST appear verbatim
  in the raw source row text, otherwise marked UNPARSED.
- Treated as untrusted data: source row text is placed only in user prompt, never system prompt.
"""

from __future__ import annotations

import re
from typing import Optional
from pydantic import BaseModel, Field

from src.config import get_logger
from src.extraction.normalize import NormalizedTestRow, normalize_raw_row
from src.llm.client import llm_client

logger = get_logger(__name__)


class LLMRowExtractionSchema(BaseModel):
    """Structured extraction output required from the LLM."""

    test_name: str = Field(description="Name or alias of the test exactly as printed")
    value_text: str = Field(description="Observed numeric or qualitative value copied verbatim from row")
    unit: str = Field(description="Unit of measurement copied verbatim from row")
    range_text: str = Field(description="Reference range or interval copied verbatim from row")


def verify_verbatim_appearance(token: str, source_text: str) -> bool:
    """Verify that an extracted token appears verbatim in the source text.

    Case-insensitive, collapsing whitespace and normalizing punctuation.
    """
    if not token or not source_text:
        return False

    def simplify(s: str) -> str:
        s = s.replace(",", "").replace(" ", "")
        return re.sub(r"[–—−]", "-", s).lower()

    clean_tok = simplify(token)
    clean_src = simplify(source_text)

    return clean_tok in clean_src


def fallback_extract_row_with_llm(
    source_row_text: str,
    page: int = 1,
    section: Optional[str] = None,
) -> NormalizedTestRow:
    """Use structured LLM to parse a difficult row, guarded by a verbatim check.

    If the LLM's returned value or range cannot be verified verbatim in the source text,
    the row is marked UNPARSED.
    """
    user_prompt = (
        "Extract the lab test fields from the following single laboratory report line.\n"
        "Copy values and reference ranges VERBATIM from the text. Do not invent or compute anything.\n\n"
        f"Line text: {source_row_text}\n"
    )

    try:
        extracted = llm_client.generate_structured(
            prompt=user_prompt,
            response_schema=LLMRowExtractionSchema,
        )

        # 1. Non-negotiable Verbatim Verification Check
        val_verbatim = verify_verbatim_appearance(extracted.value_text, source_row_text)
        range_verbatim = verify_verbatim_appearance(extracted.range_text, source_row_text)

        if not val_verbatim or not range_verbatim:
            logger.warning(
                "LLM extraction rejected: verbatim check failed on row %r (val_ok=%s, range_ok=%s)",
                source_row_text,
                val_verbatim,
                range_verbatim,
            )
            return NormalizedTestRow(
                raw_test_name=extracted.test_name or source_row_text,
                raw_value_text=extracted.value_text,
                raw_unit=extracted.unit,
                normalized_unit="",
                raw_range_text=extracted.range_text,
                normalized_range_text="",
                page=page,
                section=section,
                is_unparsed=True,
            )

        # 2. Normalize verified fields
        normalized = normalize_raw_row(
            raw_name=extracted.test_name,
            raw_val_str=extracted.value_text,
            raw_unit_str=extracted.unit,
            raw_range_str=extracted.range_text,
            page=page,
            section=section,
        )
        return normalized

    except Exception as exc:
        logger.error("LLM fallback extraction error on %r: %s", source_row_text, exc)
        return NormalizedTestRow(
            raw_test_name=source_row_text,
            raw_value_text="",
            raw_unit="",
            normalized_unit="",
            raw_range_text="",
            normalized_range_text="",
            page=page,
            section=section,
            is_unparsed=True,
        )
