"""Smoke test script for LLM connectivity and structured JSON output.

Enforces Preflight Step 3:
- Checks .env / environment variables for LLM_PROVIDER and API key.
- Never prints or logs API keys.
- Executes one harmless call with JSON-schema structured output.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from pydantic import BaseModel, Field


class SmokeResponse(BaseModel):
    message: str = Field(description="Harmless short response, e.g. OK")
    status: str = Field(description="Operational status, e.g. success")


def load_env_file(env_path: Path) -> dict[str, str]:
    """Parse a simple .env file without external dependencies."""
    env_vars: dict[str, str] = {}
    if not env_path.is_file():
        return env_vars
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip().strip("'\"")
            env_vars[key] = val
    return env_vars


def main() -> int:
    project_root = Path(__file__).resolve().parent.parent
    env_file = project_root / ".env"

    file_env = load_env_file(env_file)
    for k, v in file_env.items():
        if k not in os.environ:
            os.environ[k] = v

    provider = os.environ.get("LLM_PROVIDER", "gemini").lower()
    print(f"[*] Detected LLM Provider: {provider}")

    if provider == "gemini":
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            print("[FAIL] Missing GEMINI_API_KEY (or GOOGLE_API_KEY) in .env file or environment.")
            print("[INFO] Please create a .env file with:")
            print("       LLM_PROVIDER=gemini")
            print("       GEMINI_API_KEY=<your_gemini_api_key>")
            return 1

        try:
            import google.generativeai as genai
        except ImportError:
            print("[FAIL] google-generativeai package not installed.")
            print("       Install with: pip install google-generativeai")
            return 1

        try:
            genai.configure(api_key=api_key)
            model_name = os.environ.get("LLM_MODEL", "gemini-2.5-flash")
            
            # Configure model with structured JSON output schema
            model = genai.GenerativeModel(
                model_name=model_name,
                generation_config={
                    "response_mime_type": "application/json",
                    "response_schema": SmokeResponse,
                    "temperature": 0.0,
                },
            )

            prompt = 'Respond with message="OK" and status="success" in the required JSON format.'
            response = model.generate_content(prompt)
            raw_text = response.text.strip()
            parsed = SmokeResponse.model_validate_json(raw_text)

            if parsed.status.lower() == "success" and "OK" in parsed.message.upper():
                print(f"[PASS] Harmless structured output call succeeded on {model_name}!")
                print(f"       Response received: {parsed.model_dump_json()}")
                return 0
            else:
                print(f"[FAIL] Unexpected output: {raw_text}")
                return 1
        except Exception as exc:
            print(f"[FAIL] Error calling Gemini: {exc}")
            return 1

    elif provider == "openai":
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            print("[FAIL] Missing OPENAI_API_KEY in .env file or environment.")
            return 1
        # Implement openai smoke call when openai is selected
        print("[FAIL] OpenAI provider selected but smoke test needs openai package.")
        return 1

    elif provider == "anthropic":
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            print("[FAIL] Missing ANTHROPIC_API_KEY in .env file or environment.")
            return 1
        print("[FAIL] Anthropic provider selected but smoke test needs anthropic package.")
        return 1

    else:
        print(f"[FAIL] Unsupported LLM_PROVIDER: {provider}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
