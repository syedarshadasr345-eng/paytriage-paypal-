"""
PayTriage PayPal — OAuth 2.0 Client Credentials Authentication
Strictly conforms to phase4.md (Step 1) and RULES.md (§8, §9).
Features:
- Backend-only OAuth token retrieval with thread-safe caching.
- Proactive token expiry handling (refreshes 60s prior to expiry).
- Safe setup state when credentials are unconfigured.
- Redaction of client credentials in logs and errors.
"""

import time
import base64
import logging
import threading
from typing import Optional, Tuple
import httpx

from backend.paypal.config import (
    get_paypal_client_id,
    get_paypal_client_secret,
    is_paypal_configured,
    PAYPAL_API_BASE,
    PAYPAL_TIMEOUT_SECONDS,
    mask_credential,
)
from backend.paypal.schemas import PayPalOAuthToken

logger = logging.getLogger("paytriage.paypal.auth")


class PayPalAuthError(Exception):
    """Raised when PayPal authentication fails."""
    pass


class PayPalNotConfiguredError(PayPalAuthError):
    """Raised when PayPal credentials are not configured in environment."""
    pass


class PayPalAuthManager:
    """Manages cached PayPal OAuth access tokens with proactive refresh."""

    def __init__(self):
        self._cached_token: Optional[str] = None
        self._expires_at: float = 0.0
        self._lock = threading.Lock()

    def clear_cache(self) -> None:
        """Reset token cache (useful in tests)."""
        with self._lock:
            self._cached_token = None
            self._expires_at = 0.0

    def get_access_token(self, client: Optional[httpx.Client] = None) -> str:
        """Retrieve valid PayPal access token from cache or request fresh token."""
        now = time.time()
        with self._lock:
            # Refresh 60 seconds before expiration
            if self._cached_token and now < (self._expires_at - 60):
                return self._cached_token

            token, expires_at = self._fetch_new_token(client=client)
            self._cached_token = token
            self._expires_at = expires_at
            return token

    def _fetch_new_token(self, client: Optional[httpx.Client] = None) -> Tuple[str, float]:
        """Request OAuth token from POST /v1/oauth2/token using HTTP Basic Auth."""
        client_id = get_paypal_client_id()
        client_secret = get_paypal_client_secret()

        if not client_id or not client_secret:
            raise PayPalNotConfiguredError(
                "PayPal Sandbox is not configured. "
                "Please configure PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET in backend/.env."
            )

        token_url = f"{PAYPAL_API_BASE}/v1/oauth2/token"
        credentials = f"{client_id}:{client_secret}".encode("utf-8")
        basic_auth = base64.b64encode(credentials).decode("utf-8")

        headers = {
            "Accept": "application/json",
            "Accept-Language": "en_US",
            "Authorization": f"Basic {basic_auth}",
        }
        data = {"grant_type": "client_credentials"}

        logger.info(f"Requesting PayPal OAuth token from {token_url} (client_id={mask_credential(client_id)})")

        try:
            http = client or httpx.Client(timeout=PAYPAL_TIMEOUT_SECONDS)
            resp = http.post(token_url, headers=headers, data=data)

            if resp.status_code == 200:
                parsed = PayPalOAuthToken.model_validate(resp.json())
                expiry_timestamp = time.time() + parsed.expires_in
                logger.info(f"PayPal OAuth token retrieved successfully (expires_in={parsed.expires_in}s)")
                return parsed.access_token, expiry_timestamp
            elif resp.status_code in (401, 403):
                logger.error(f"PayPal OAuth authentication rejected (HTTP {resp.status_code}): Invalid client credentials")
                raise PayPalAuthError(
                    f"PayPal Sandbox authentication failed (HTTP {resp.status_code}): Invalid client ID or secret."
                )
            else:
                logger.error(f"PayPal OAuth token request failed (HTTP {resp.status_code}): {resp.text[:200]}")
                raise PayPalAuthError(
                    f"PayPal OAuth endpoint returned unexpected HTTP {resp.status_code}."
                )

        except (httpx.TimeoutException, TimeoutError) as te:
            logger.error(f"PayPal OAuth request timed out: {te}")
            raise PayPalAuthError(f"PayPal OAuth request timed out after {PAYPAL_TIMEOUT_SECONDS}s.")
        except httpx.RequestError as re:
            logger.error(f"PayPal OAuth network transport error: {re}")
            raise PayPalAuthError(f"PayPal network error: Unable to connect to PayPal API base ({PAYPAL_API_BASE}).")


# Singleton authentication manager
_default_auth_manager = PayPalAuthManager()


def get_auth_manager() -> PayPalAuthManager:
    """Retrieve global PayPal authentication manager."""
    return _default_auth_manager


def get_paypal_access_token() -> str:
    """Convenience helper to retrieve current access token."""
    return _default_auth_manager.get_access_token()

