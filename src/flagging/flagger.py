"""Deterministic flagging engine for laboratory test results.

Enforces:
- Code decides, the LLM explains. The LLM never decides a flag.
- Flag ONLY against the range printed on the report.
- The KB typical_range_info is purely informational and NEVER read here.
- Inclusive limits: value == lower_limit or value == upper_limit is strictly NORMAL.
- Implausible values outside KB plausible_value_bounds -> NEEDS_REVIEW.
- Multi-tier, unparseable, or missing ranges -> NEEDS_REVIEW.
"""

from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field

from src.data.loaders import load_knowledge_base
from src.data.models import KnowledgeBase, KBBloodTest
from src.flagging.range_parser import parse_reference_range
from src.flagging.units import check_unit_compatibility


class FlaggingResult(BaseModel):
    """Deterministic result of evaluating an observed value against its printed range."""

    flag: str  # NORMAL, LOW, HIGH, NEEDS_REVIEW
    ref_low: Optional[float] = None
    ref_high: Optional[float] = None
    range_type: str  # between, upper, lower, qualitative, multi_tier, sex_specific, unparseable
    explanation_needed: bool = False
    is_implausible: bool = False
    warnings: list[str] = Field(default_factory=list)


def flag_test_result(
    value: Optional[float],
    value_text: str,
    range_text: str,
    patient_sex: Optional[str] = None,
    test_id: Optional[str] = None,
    unit: Optional[str] = None,
    kb: Optional[KnowledgeBase] = None,
) -> FlaggingResult:
    """Evaluate observed test result strictly against the printed range on the report.

    Limits are strictly inclusive:
        value == low_limit  -> NORMAL
        value == high_limit -> NORMAL
    """
    warnings: list[str] = []

    # 1. Parse printed range
    parsed_range = parse_reference_range(range_text)
    r_type = parsed_range.range_type

    # 2. Check for multi-tier or unparseable ranges -> NEEDS_REVIEW
    if r_type == "multi_tier":
        return FlaggingResult(
            flag="NEEDS_REVIEW",
            range_type=r_type,
            explanation_needed=True,
            warnings=["Multi-tier reference criteria require review with your doctor."],
        )

    if not parsed_range.is_valid or r_type == "unparseable":
        return FlaggingResult(
            flag="NEEDS_REVIEW",
            range_type="unparseable",
            explanation_needed=True,
            warnings=["Printed reference range could not be parsed deterministically."],
        )

    # 3. Handle qualitative results (e.g. Urine Glucose: Negative)
    if r_type == "qualitative":
        clean_val = value_text.strip().lower()
        normal_set = parsed_range.qualitative_normal_set or {"negative", "nil", "non-reactive", "absent", "normal"}
        if clean_val in normal_set:
            return FlaggingResult(flag="NORMAL", range_type=r_type, explanation_needed=False)
        else:
            return FlaggingResult(flag="HIGH", range_type=r_type, explanation_needed=True)

    # 4. Resolve sex-specific single-cell ranges
    low: Optional[float] = None
    high: Optional[float] = None

    if r_type == "sex_specific":
        if not patient_sex:
            return FlaggingResult(
                flag="NEEDS_REVIEW",
                range_type=r_type,
                explanation_needed=True,
                warnings=["Sex-specific range requires patient sex, which was not detected."],
            )

        sex_lower = patient_sex.strip().lower()
        if sex_lower == "male" and parsed_range.male_range:
            low, high = parsed_range.male_range
        elif sex_lower == "female" and parsed_range.female_range:
            low, high = parsed_range.female_range
        else:
            return FlaggingResult(
                flag="NEEDS_REVIEW",
                range_type=r_type,
                explanation_needed=True,
                warnings=[f"Unrecognized or unmatched patient sex: {patient_sex}"],
            )
    else:
        low = parsed_range.low
        high = parsed_range.high

    # 5. Missing numeric value
    if value is None:
        return FlaggingResult(
            flag="NEEDS_REVIEW",
            ref_low=low,
            ref_high=high,
            range_type=r_type,
            explanation_needed=True,
            warnings=["Numeric value is missing or unparsed."],
        )

    # 6. Clinical plausibility guard against KB plausible_value_bounds
    if test_id and value is not None:
        loaded_kb = kb or load_knowledge_base()
        test_entry = next((t for t in loaded_kb.blood_tests if t.test_id == test_id), None)
        if test_entry and len(test_entry.plausible_value_bounds) == 2:
            p_min, p_max = test_entry.plausible_value_bounds
            
            # Convert value to standard unit for plausibility check if an alternate unit was used
            val_in_std = value
            if unit:
                clean_u = unit.strip().lower()
                for alt in test_entry.alternate_units:
                    if alt.unit.strip().lower() == clean_u and alt.conversion_factor:
                        val_in_std = value / alt.conversion_factor
                        break

            if val_in_std < p_min or val_in_std > p_max:
                return FlaggingResult(
                    flag="NEEDS_REVIEW",
                    ref_low=low,
                    ref_high=high,
                    range_type=r_type,
                    explanation_needed=True,
                    is_implausible=True,
                    warnings=[
                        f"Observed value {value} falls outside plausible clinical bounds ({p_min} - {p_max}). "
                        "Likely an extraction or laboratory printing anomaly."
                    ],
                )

    # 7. Check unit compatibility warnings
    if unit and test_id:
        is_compat, unit_warn = check_unit_compatibility(test_id, unit, kb)
        if not is_compat and unit_warn:
            warnings.append(unit_warn)

    # 8. Deterministic boundary evaluation with INCLUSIVE limits
    if r_type == "upper":
        # e.g. "< 200", "<= 1.2"
        if high is not None and value <= high:
            return FlaggingResult(
                flag="NORMAL", ref_low=None, ref_high=high, range_type=r_type, explanation_needed=False, warnings=warnings
            )
        else:
            return FlaggingResult(
                flag="HIGH", ref_low=None, ref_high=high, range_type=r_type, explanation_needed=True, warnings=warnings
            )

    if r_type == "lower":
        # e.g. "> 40", ">= 50"
        if low is not None and value >= low:
            return FlaggingResult(
                flag="NORMAL", ref_low=low, ref_high=None, range_type=r_type, explanation_needed=False, warnings=warnings
            )
        else:
            return FlaggingResult(
                flag="LOW", ref_low=low, ref_high=None, range_type=r_type, explanation_needed=True, warnings=warnings
            )

    if r_type in {"between", "sex_specific"}:
        if low is not None and high is not None:
            if value < low:
                return FlaggingResult(
                    flag="LOW", ref_low=low, ref_high=high, range_type=r_type, explanation_needed=True, warnings=warnings
                )
            elif value > high:
                return FlaggingResult(
                    flag="HIGH", ref_low=low, ref_high=high, range_type=r_type, explanation_needed=True, warnings=warnings
                )
            else:
                # Value == low or value == high or between -> NORMAL
                return FlaggingResult(
                    flag="NORMAL", ref_low=low, ref_high=high, range_type=r_type, explanation_needed=False, warnings=warnings
                )

    return FlaggingResult(
        flag="NEEDS_REVIEW",
        ref_low=low,
        ref_high=high,
        range_type=r_type,
        explanation_needed=True,
        warnings=["Unresolved range evaluation."],
    )
