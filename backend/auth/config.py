"""
PayTriage Auth — Configuration & Session Token Utilities
Strictly conforms to phase5.md and RULES.md (§7, §9).
"""

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any

DEMO_USER = os.getenv("DEMO_USER", "merchant@example.com")
DEMO_PASSWORD = os.getenv("DEMO_PASSWORD", "paytriage2026")
SESSION_SECRET = os.getenv("SESSION_SECRET", "paytriage_session_secret_min_32_chars_2026")
DEFAULT_MERCHANT_ID = "merchant_demo"

# Secure PBKDF2 Password Hashing (only the hash is stored/compared)
_SALT = b"paytriage_static_salt_secure_2026"


def hash_password(password: str) -> str:
    """Hash password using PBKDF2-HMAC-SHA256."""
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), _SALT, 100000)
    return key.hex()


# Precomputed hash of default/configured demo credentials
DEMO_PASSWORD_HASH = hash_password(DEMO_PASSWORD)


def verify_password(plain_password: str) -> bool:
    """Verify submitted plaintext against stored hash."""
    submitted_hash = hash_password(plain_password)
    return hmac.compare_digest(submitted_hash, DEMO_PASSWORD_HASH)


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
    payload = {
        "sub": user_email,
        "merchant_id": merchant_id,
        "role": role,  # 'merchant' or 'ai'
        "exp": int(time.time()) + (expires_in_hours * 3600),
    }
    payload_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    payload_b64 = _b64url_encode(payload_bytes)

    sig = hmac.new(
        SESSION_SECRET.encode("utf-8"),
        payload_b64.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    sig_b64 = _b64url_encode(sig)

    return f"{payload_b64}.{sig_b64}"


def verify_session_token(token: str) -> dict[str, Any] | None:
    """Verify HMAC signature and expiration of a session token. Returns payload dict or None."""
    if not token or "." not in token:
        return None
    try:
        parts = token.split(".")
        if len(parts) != 2:
            return None
        payload_b64, sig_b64 = parts

        expected_sig = hmac.new(
            SESSION_SECRET.encode("utf-8"),
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

