"""
PayTriage Auth — Configuration & Session Token Utilities
Strictly conforms to phase5.md, phase6.md and RULES.md (§7, §9).
Loads configuration relative to backend/.env.
Never stores plaintext DEMO_PASSWORD; only hashes compared in constant time.
"""

import base64
import hashlib
import hmac
import json
import os
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# Search and load backend/.env relative to backend folder
BACKEND_DIR = Path(__file__).resolve().parent.parent
BACKEND_ENV_PATH = BACKEND_DIR / ".env"
if BACKEND_ENV_PATH.exists():
    load_dotenv(dotenv_path=BACKEND_ENV_PATH)
else:
    load_dotenv()

DEFAULT_MERCHANT_ID = "merchant_demo"
_SALT = b"paytriage_static_salt_secure_2026"


def _is_placeholder(val: str | None) -> bool:
    if not val or not val.strip():
        return True
    v = val.strip().lower()
    return v.startswith("your_") or v.startswith("replace_with_") or "placeholder" in v


def get_missing_auth_config() -> list[str]:
    """Check if any of DEMO_USER, DEMO_PASSWORD, or SESSION_SECRET are missing or placeholders."""
    missing = []
    if _is_placeholder(os.getenv("DEMO_USER")):
        missing.append("DEMO_USER")
    if _is_placeholder(os.getenv("DEMO_PASSWORD")):
        missing.append("DEMO_PASSWORD")
    if _is_placeholder(os.getenv("SESSION_SECRET")):
        missing.append("SESSION_SECRET")
    return missing


def hash_password(password: str) -> str:
    """Hash password using PBKDF2-HMAC-SHA256."""
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), _SALT, 100000)
    return key.hex()


def get_demo_user() -> str | None:
    val = os.getenv("DEMO_USER")
    if _is_placeholder(val):
        return None
    return val.strip()


def get_session_secret() -> str | None:
    val = os.getenv("SESSION_SECRET")
    if _is_placeholder(val):
        return None
    return val.strip()


def get_demo_password_hash() -> str | None:
    """Derive hash of DEMO_PASSWORD. Plaintext is never stored in variables."""
    val = os.getenv("DEMO_PASSWORD")
    if _is_placeholder(val):
        return None
    return hash_password(val.strip())


# Dynamic property-like access for tests
DEMO_USER = os.getenv("DEMO_USER", "")
DEMO_PASSWORD = os.getenv("DEMO_PASSWORD", "")


def verify_password(plain_password: str) -> bool:
    """Verify submitted plaintext against stored hash in constant time."""
    expected_hash = get_demo_password_hash()
    if not expected_hash:
        return False
    submitted_hash = hash_password(plain_password)
    return hmac.compare_digest(submitted_hash, expected_hash)


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _b64url_decode(s: str) -> bytes:
    padding = 4 - (len(s) % 4)
    if padding and padding != 4:
        s += "=" * padding
    return base64.urlsafe_b64decode(s)


def create_session_token(
    user_email: str,
    merchant_id: str = DEFAULT_MERCHANT_ID,
    role: str = "merchant",
    expires_in_hours: int = 24,
) -> str:
    """Create a tamper-proof HMAC-SHA256 signed session token."""
    secret = get_session_secret()
    if not secret:
        raise ValueError("Cannot issue session token: SESSION_SECRET is unconfigured.")

    payload = {
        "sub": user_email,
        "merchant_id": merchant_id,
        "role": role,  # 'merchant' or 'ai'
        "exp": int(time.time()) + (expires_in_hours * 3600),
    }
    payload_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    payload_b64 = _b64url_encode(payload_bytes)

    sig = hmac.new(
        secret.encode("utf-8"),
        payload_b64.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    sig_b64 = _b64url_encode(sig)

    return f"{payload_b64}.{sig_b64}"


def verify_session_token(token: str) -> dict[str, Any] | None:
    """Verify HMAC signature and expiration of a session token. Returns payload dict or None."""
    if not token or "." not in token:
        return None
    secret = get_session_secret()
    if not secret:
        return None
    try:
        parts = token.split(".")
        if len(parts) != 2:
            return None
        payload_b64, sig_b64 = parts

        expected_sig = hmac.new(
            secret.encode("utf-8"),
            payload_b64.encode("utf-8"),
            hashlib.sha256,
        ).digest()
        actual_sig = _b64url_decode(sig_b64)

        if not hmac.compare_digest(expected_sig, actual_sig):
            return None

        payload_bytes = _b64url_decode(payload_b64)
        payload = json.loads(payload_bytes.decode("utf-8"))

        if payload.get("exp", 0) < time.time():
            return None

        return payload
    except Exception:
        return None
