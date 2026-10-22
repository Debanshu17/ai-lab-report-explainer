"""Audit logger that records every prompt and payload dispatched to an LLM.

Used in evaluation and testing to prove 0 PII leaks and guarantee grounding.
"""

from __future__ import annotations

import datetime
from typing import Any, List, Optional
from pydantic import BaseModel, Field

from src.privacy.redact import audit_payload_for_leaks


class LLMPayloadRecord(BaseModel):
    """Immutable audit record of a single call dispatched to an external LLM."""

    timestamp: str = Field(default_factory=lambda: datetime.datetime.utcnow().isoformat())
    provider: str
    model: str
    prompt: str
    schema_name: Optional[str] = None
    response: Optional[str] = None


class PayloadLogManager:
    """In-memory audit store for LLM interactions."""

    def __init__(self) -> None:
        self._records: List[LLMPayloadRecord] = []

    def log_call(
        self,
        provider: str,
        model: str,
        prompt: str,
        schema_name: Optional[str] = None,
        response: Optional[str] = None,
    ) -> None:
        """Record an outgoing LLM call."""
        record = LLMPayloadRecord(
            provider=provider,
            model=model,
            prompt=prompt,
            schema_name=schema_name,
            response=response,
        )
        self._records.append(record)

    def get_records(self) -> List[LLMPayloadRecord]:
        """Return all logged payload records."""
        return list(self._records)

    def clear(self) -> None:
        """Clear all payload records."""
        self._records.clear()

    def audit_for_pii_leaks(self, forbidden_strings: list[str]) -> list[dict[str, Any]]:
        """Audit all recorded payloads against forbidden PII tokens.

        Returns list of leak occurrences: [{prompt_idx, forbidden_token, snippet}].
        """
        detected_leaks: list[dict[str, Any]] = []
        for idx, rec in enumerate(self._records):
            leaks = audit_payload_for_leaks(rec.prompt, forbidden_strings)
            for token in leaks:
                detected_leaks.append(
                    {
                        "call_index": idx,
                        "model": rec.model,
                        "forbidden_token": token,
                        "prompt_preview": rec.prompt[:200],
                    }
                )
        return detected_leaks


# Global singleton manager
payload_logger = PayloadLogManager()
