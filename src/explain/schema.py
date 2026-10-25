"""Pydantic schemas for test explanations and report-level educational summaries."""

from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field

from src.data.models import KBSource


class TestExplanation(BaseModel):
    """Educational explanation for a single lab test row."""

    # Prevent pytest from mistaking this model for a test class
    __test__ = False

    test_name: str = Field(description="Display test name from the report")
    test_id: str = Field(description="Canonical test_id or UNKNOWN")
    observed_value: Optional[float] = Field(default=None, description="Observed numeric value")
    unit: str = Field(default="", description="Unit of measurement printed on the report")
    reference_interval: str = Field(default="", description="Printed reference interval")
    flag: str = Field(description="Deterministic flag: NORMAL, LOW, HIGH, or NEEDS_REVIEW")
    what_it_measures: str = Field(description="Curated clinical description of what the test measures")
    what_your_value_means: str = Field(description="Educational explanation of the value within or outside printed range")
    factors_that_can_affect_result: list[str] = Field(
        default_factory=list, description="Common non-diagnostic factors (hydration, fasting, etc.)"
    )
    when_to_talk_to_doctor: str = Field(
        description="Guidance on when to consult a healthcare provider"
    )
    questions_for_doctor: list[str] = Field(
        default_factory=list, description="Recommended educational questions to ask the doctor (typically 3)"
    )
    sources: list[KBSource] = Field(default_factory=list, description="Source citations for medical facts")
    source_verification: str = Field(default="unverified", description="Verification status of cited sources")
    needs_verification: bool = Field(default=True, description="Whether this KB entry has pending human verification")
    is_fallback: bool = Field(default=False, description="True if no trusted KB explanation was available")
    language: str = Field(default="en", description="Explanation language: 'en' or 'hi'")


class ReportExplanation(BaseModel):
    """Complete educational explanation for an uploaded lab report."""

    disclaimer: str = Field(description="Unequivocal code-injected educational disclaimer")
    tests: list[TestExplanation] = Field(description="List of explanations per extracted test")
    summary: str = Field(description="High-level educational overview of report findings")
    urgent_care_footer: Optional[str] = Field(
        default=None, description="Emergency medical care notice if critical conditions are met"
    )
    mode: str = Field(description="Explanation mode used: 'kb_template' or 'llm_grounded'")
    language: str = Field(default="en", description="Language of explanation: 'en' or 'hi'")
