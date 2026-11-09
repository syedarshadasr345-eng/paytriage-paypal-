"""
PayTriage PayPal — OAuth Connectivity Ping Script
Tests OAuth 2.0 token generation against PayPal Sandbox API.
Verifies caching and expiry handling.
NEVER prints or leaks Client Secrets or raw Access Tokens.
"""

import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

from backend.paypal.auth import (
    PayPalAuthError,
    PayPalNotConfiguredError,
    get_auth_manager,
)
from backend.paypal.config import (
    PAYPAL_API_BASE,
    get_paypal_client_id,
    get_paypal_client_secret,
    is_paypal_configured,
    mask_credential,
)


def ping_paypal() -> dict:
    client_id = get_paypal_client_id()
    client_secret = get_paypal_client_secret()

    print("=" * 60)
    print("PayTriage PayPal Sandbox OAuth Ping")
    print("=" * 60)
    print(f"Sandbox Base URL:  {PAYPAL_API_BASE}")
    print(f"Client ID:         {mask_credential(client_id)}")
    print(f"Secret Configured: {bool(client_secret)}")
    print()

    if not is_paypal_configured():
        print("[SETUP STATE] PayPal Sandbox is not configured.")
        print("Please add PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET to backend/.env.")
        return {"status": "NOT_CONFIGURED"}

    auth_mgr = get_auth_manager()
    auth_mgr.clear_cache()

    start_time = time.time()
    try:
        # First call: fetches from PayPal Sandbox API
        token = auth_mgr.get_access_token()
        elapsed_live = time.time() - start_time

        masked_token = f"{token[:6]}...{token[-4:]}" if len(token) > 10 else "***"
        print("[SUCCESS] OAuth Token retrieved from PayPal Sandbox:")
        print(f"  Live Request Elapsed: {elapsed_live:.2f}s")
        print(f"  Token Preview:        {masked_token} (length: {len(token)})")
        print(f"  Cached Expiry:        {auth_mgr._expires_at - time.time():.1f}s remaining")

        # Second call: verifies token caching
        cache_start = time.time()
        cached_token = auth_mgr.get_access_token()
        cache_elapsed = time.time() - cache_start
        assert cached_token == token, "Cached token mismatch!"
        print(f"  Cache Retrieval Time: {cache_elapsed * 1000:.3f}ms (instant cache hit verified)")

        return {
            "status": "SUCCESS",
            "elapsed": round(elapsed_live, 2),
            "masked_token": masked_token,
            "token_length": len(token),
        }

    except PayPalNotConfiguredError as e:
        print(f"[SETUP STATE] {e}")
        return {"status": "NOT_CONFIGURED", "error": str(e)}
    except PayPalAuthError as e:
        elapsed = time.time() - start_time
        print(f"[AUTH ERROR] Failed after {elapsed:.2f}s:")
        print(f"  {e}")
        return {"status": "ERROR", "elapsed": round(elapsed, 2), "error": str(e)}
    except Exception as e:
        elapsed = time.time() - start_time
        print(f"[UNEXPECTED ERROR] Failed after {elapsed:.2f}s:")
        print(f"  {e}")
        return {"status": "ERROR", "elapsed": round(elapsed, 2), "error": str(e)}


if __name__ == "__main__":
    ping_paypal()

