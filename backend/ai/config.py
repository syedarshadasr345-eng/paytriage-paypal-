"""
PayTriage AI — AI Configuration & Environment Settings
Strictly conforms to phase3.md and RULES.md (§4, §6).
Reads GEMINI_API_KEY from backend/.env or system environment.
"""

import os
import re
import logging
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

# Search and load backend/.env first, then root .env
BACKEND_DIR = Path(__file__).resolve().parent.parent
BACKEND_ENV_PATH = BACKEND_DIR / ".env"
ROOT_ENV_PATH = BACKEND_DIR.parent / ".env"

if BACKEND_ENV_PATH.exists():
    load_dotenv(dotenv_path=BACKEND_ENV_PATH)
elif ROOT_ENV_PATH.exists():
    load_dotenv(dotenv_path=ROOT_ENV_PATH)
else:
    load_dotenv()

# Active Gemini production model (Current official GenAI SDK standard)
DEFAULT_GEMINI_MODEL = "gemini-3.8-flash"
GEMINI_MODEL = os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)

# Operational limits
AI_TIMEOUT_SECONDS = float(os.getenv("AI_TIMEOUT_SECONDS", "30.0"))
AI_MAX_RETRIES = int(os.getenv("AI_MAX_RETRIES", "1"))
AI_FORCE_IPV4 = os.getenv("AI_FORCE_IPV4", "true").lower() in ("true", "1", "yes")

logger = logging.getLogger("paytriage.ai")


def get_gemini_api_key() -> Optional[str]:
    """Retrieve Gemini API key strictly from environment.
    Never hardcoded. Returns None if unconfigured.
    """
    key = os.getenv("GEMINI_API_KEY")
    if key and key.strip() and not key.startswith("your_"):
        return key.strip()
    return None


def is_gemini_available() -> bool:
    """Check if a valid real Gemini API key is configured."""
    return get_gemini_api_key() is not None


def mask_secret(secret: Optional[str]) -> str:
    """Mask sensitive tokens or API keys for safe telemetry."""
    if not secret:
        return "[NOT_SET]"
    if len(secret) <= 8:
        return "***"
    return f"{secret[:4]}...{secret[-4:]}"


def redact_sensitive_data(text: str) -> str:
    """Sanitize text to prevent logging secrets, tokens, or PII."""
    if not text:
        return ""
    # Redact potential API keys (AIza..., sk-..., etc.)
    text = re.sub(r"AIza[0-9A-Za-z-_]{35}", "[REDACTED_API_KEY]", text)
    text = re.sub(r"sk-[0-9A-Za-z-_]{20,}", "[REDACTED_SECRET]", text)
    # Redact email addresses from raw error traces
    text = re.sub(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", "[REDACTED_EMAIL]", text)
    return text
