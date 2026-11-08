"""
PayTriage PayPal — Configuration & Environment Settings
Strictly conforms to phase4.md and RULES.md (§8, §9).
Reads PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET, and PAYPAL_API_BASE from backend/.env or system environment.
"""

import os
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

logger = logging.getLogger("paytriage.paypal")

# Environment & Endpoints
PAYPAL_MODE = os.getenv("PAYPAL_MODE", "sandbox").lower()
DEFAULT_SANDBOX_BASE = "https://api-m.sandbox.paypal.com"
DEFAULT_LIVE_BASE = "https://api-m.paypal.com"

PAYPAL_API_BASE = os.getenv(
    "PAYPAL_API_BASE",
    DEFAULT_SANDBOX_BASE if PAYPAL_MODE == "sandbox" else DEFAULT_LIVE_BASE,
).rstrip("/")

# Strict Sandbox enforcement per RULES.md §8: Never connect to live environment
if PAYPAL_MODE != "sandbox" and "sandbox" not in PAYPAL_API_BASE:
    logger.warning("PAYPAL_MODE is not sandbox. Overriding to sandbox for security compliance.")
    PAYPAL_MODE = "sandbox"
    PAYPAL_API_BASE = DEFAULT_SANDBOX_BASE

# Operational limits
PAYPAL_TIMEOUT_SECONDS = float(os.getenv("PAYPAL_TIMEOUT_SECONDS", "15.0"))
PAYPAL_MAX_RETRIES = int(os.getenv("PAYPAL_MAX_RETRIES", "1"))


def get_paypal_client_id() -> Optional[str]:
    """Retrieve PayPal Sandbox Client ID. Returns None if unconfigured or placeholder."""
    cid = os.getenv("PAYPAL_CLIENT_ID")
    if cid and cid.strip() and not cid.startswith("your_"):
        return cid.strip()
    return None


def get_paypal_client_secret() -> Optional[str]:
    """Retrieve PayPal Sandbox Client Secret. Returns None if unconfigured or placeholder."""
    secret = os.getenv("PAYPAL_CLIENT_SECRET")
    if secret and secret.strip() and not secret.startswith("your_"):
        return secret.strip()
    return None


def is_paypal_configured() -> bool:
    """Return True only if genuine, non-placeholder credentials are provided."""
    cid = get_paypal_client_id()
    sec = get_paypal_client_secret()
    return bool(cid and sec)


def mask_credential(val: Optional[str]) -> str:
    """Mask credential for safe logging and telemetry."""
    if not val:
        return "[NOT_SET]"
    if len(val) <= 8:
        return "***"
    return f"{val[:4]}...{val[-4:]}"

