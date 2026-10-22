"""Pydantic data models for CSV lab database and Knowledge Base.

Enforces strict schemas, fail-loud validations, and type safety.
"""

from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field, field_validator


class CSVLabRow(BaseModel):
    """Schema for a single row from ai_lab_report_database.csv."""

    Patient_ID: str = Field(description="Unique patient identifier, e.g. P001")
    Patient_Name: str = Field(description="Fictional patient full name")
    Age: int = Field(ge=0, le=150, description="Patient age in years")
    Gender: str = Field(description="Patient sex/gender (Male or Female)")
    Clinical_Context: str = Field(
        description="Diagnostic-style label. FORBIDDEN from PDF printing or LLM exposure."
    )
    Test_Name: str = Field(description="Name of the laboratory test")
    Observed_Value: float = Field(description="Numeric observed result")
    Unit: str = Field(description="Unit of measurement")
    Reference_Interval: str = Field(description="Low-high reference range string printed on report")

    @field_validator("Gender")
    @classmethod
    def validate_gender(cls, v: str) -> str:
        clean = v.strip().capitalize()
        if clean not in {"Male", "Female"}:
            raise ValueError(f"Gender must be 'Male' or 'Female', got: {v}")
        return clean

    @field_validator("Reference_Interval")
    @classmethod
    def validate_reference_interval(cls, v: str) -> str:
        v_clean = v.strip()
        if not v_clean:
            raise ValueError("Reference_Interval cannot be empty")
        return v_clean


class KBSource(BaseModel):
    """Source reference for a knowledge base entry."""

    source_name: str
    url: str
    license_note: str
    retrieved_date: Optional[str] = None
    verification: str = Field(
        description="Either 'page_content_read_by_assistant' or 'url_confirmed_content_not_read'"
    )


class KBAlternateUnit(BaseModel):
    """Alternate unit definition with conversion factor or formula."""

    unit: str
    conversion_factor: Optional[float] = None
    formula: Optional[str] = None
    note: Optional[str] = None


class KBBloodTest(BaseModel):
    """Schema for a curated blood test entry in the Knowledge Base."""

    test_id: str
    test_name: str
    test_name_hindi: str
    test_name_transliteration: str
    aliases: list[str]
    category: str
    standard_unit: str
    alternate_units: list[KBAlternateUnit]
    plausible_value_bounds: list[float]
    typical_range_info: str
    clinical_summary: str
    general_context_low: str
    general_context_high: str
    factors_that_can_affect_result: list[str]
    when_to_talk_to_a_doctor: str
    questions_for_doctor: list[str]
    hindi_summary: str
    hindi_reviewed: bool
    last_reviewed: str
    needs_verification: bool
    sources: list[KBSource]


class KBGeneralTopic(BaseModel):
    """Schema for a curated general educational topic."""

    topic_id: str
    title: str
    summary: str
    sources: list[KBSource] = Field(default_factory=list)
    source_note: Optional[str] = None
    needs_verification: bool


class KBMetadata(BaseModel):
    """Metadata for the Knowledge Base."""

    purpose: str
    last_edited: str
    range_note: str
    verification_legend: dict[str, str]
    needs_verification_note: str
    hindi_note: str


class KnowledgeBase(BaseModel):
    """Top-level Knowledge Base container."""

    general_topics: list[KBGeneralTopic]
    blood_tests: list[KBBloodTest]
    metadata: KBMetadata
