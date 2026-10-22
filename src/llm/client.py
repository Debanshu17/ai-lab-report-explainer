"""Provider-agnostic LLM client with structured JSON output and audit logging.

Default provider: Gemini.
Configurable via .env (GEMINI_API_KEY, OPENAI_API_KEY, ANTHROPIC_API_KEY).
"""

from __future__ import annotations

import json
import time
from typing import Any, Optional, Type, TypeVar
from pydantic import BaseModel

from src.config import settings, get_logger
from src.llm.payload_log import payload_logger

logger = get_logger(__name__)

T = TypeVar("T", bound=BaseModel)


class LLMClient:
    """Unified provider-agnostic LLM interface."""

    def __init__(self) -> None:
        self.provider = settings.LLM_PROVIDER.lower()
        self.model_name = settings.LLM_MODEL
        self.temperature = settings.LLM_TEMPERATURE
        self._gemini_client = None
        self._init_provider()

    def _init_provider(self) -> None:
        if self.provider == "gemini":
            api_key = settings.GEMINI_API_KEY
            if not api_key:
                logger.warning("GEMINI_API_KEY is not configured.")
                return
            try:
                import google.generativeai as genai
                genai.configure(api_key=api_key)
                self._gemini_client = genai
            except ImportError:
                logger.error("google-generativeai package is not installed.")

    def generate_structured(
        self,
        prompt: str,
        response_schema: Type[T],
        max_retries: int = 2,
    ) -> T:
        """Execute a prompt requiring strict Pydantic JSON structured output.

        All payloads are logged to payload_logger for PII verification.
        """
        schema_name = response_schema.__name__

        if self.provider == "gemini":
            if not self._gemini_client:
                raise RuntimeError("Gemini client not initialized. Check GEMINI_API_KEY.")

            last_error: Optional[Exception] = None
            for attempt in range(max_retries + 1):
                try:
                    model = self._gemini_client.GenerativeModel(
                        model_name=self.model_name,
                        generation_config={
                            "response_mime_type": "application/json",
                            "response_schema": response_schema,
                            "temperature": self.temperature,
                        },
                    )

                    response = model.generate_content(prompt)
                    raw_text = response.text.strip()

                    # Record in audit log
                    payload_logger.log_call(
                        provider="gemini",
                        model=self.model_name,
                        prompt=prompt,
                        schema_name=schema_name,
                        response=raw_text,
                    )

                    parsed = response_schema.model_validate_json(raw_text)
                    return parsed
                except Exception as exc:
                    last_error = exc
                    logger.warning("LLM call attempt %d failed: %s", attempt + 1, exc)
                    if attempt < max_retries:
                        time.sleep(1.0 * (attempt + 1))

            # Record failure in audit log
            payload_logger.log_call(
                provider="gemini",
                model=self.model_name,
                prompt=prompt,
                schema_name=schema_name,
                response=f"[ERROR] {last_error}",
            )
            raise RuntimeError(f"Structured LLM generation failed after {max_retries + 1} attempts: {last_error}") from last_error

        elif self.provider == "openai":
            raise NotImplementedError("OpenAI provider not enabled in this configuration.")
        elif self.provider == "anthropic":
            raise NotImplementedError("Anthropic provider not enabled in this configuration.")
        else:
            raise ValueError(f"Unsupported LLM provider: {self.provider}")


# Global client instance
llm_client = LLMClient()
