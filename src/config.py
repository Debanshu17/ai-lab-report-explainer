"""Configuration and environment settings using pydantic-settings.

Enforces privacy, configurable LLM providers, modes, and secure logging.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment or .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Provider & Model Settings
    LLM_PROVIDER: str = "gemini"
    LLM_MODEL: str = "gemini-2.5-flash"
    GEMINI_API_KEY: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None
    ANTHROPIC_API_KEY: Optional[str] = None
    LLM_TEMPERATURE: float = 0.0

    # Operational Modes
    EXTRACTION_MODE: str = "rules_plus_verified_llm"  # rules_only, llm_only, rules_plus_verified_llm
    EXPLANATION_MODE: str = "llm_grounded"            # kb_template, llm_grounded

    # Storage Paths
    DATA_INPUTS_DIR: Path = Path("data/inputs")
    CHROMA_PERSIST_DIRECTORY: Path = Path("data/chroma")
    EMBEDDING_MODEL: str = "BAAI/bge-small-en-v1.5"

    # Safety & Thresholds
    ALIAS_FUZZY_THRESHOLD: float = 85.0
    EMBEDDING_SIMILARITY_THRESHOLD: float = 0.65
    MAX_FILE_SIZE_MB: int = 5
    MAX_PDF_PAGES: int = 10


settings = Settings()


class PIIMaskingFilter(logging.Filter):
    """Log filter that redacts common PII patterns and secrets."""

    PHONE_REGEX = re.compile(r"\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b")
    EMAIL_REGEX = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b")
    API_KEY_REGEX = re.compile(r"\b(AIzaSy[A-Za-z0-9_-]{33}|sk-[A-Za-z0-9_-]{20,})\b")

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            msg = self.PHONE_REGEX.sub("[REDACTED_PHONE]", record.msg)
            msg = self.EMAIL_REGEX.sub("[REDACTED_EMAIL]", msg)
            msg = self.API_KEY_REGEX.sub("[REDACTED_KEY]", msg)
            record.msg = msg
        return True


def get_logger(name: str) -> logging.Logger:
    """Return a logger configured with PII masking."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s")
        handler.setFormatter(formatter)
        handler.addFilter(PIIMaskingFilter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger
