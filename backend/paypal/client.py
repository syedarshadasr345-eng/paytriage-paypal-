"""
PayTriage PayPal — Base REST API Client with Idempotency & Error Handling
Strictly conforms to phase4.md and RULES.md (§8, §9).
Features:
- Bearer token authentication with auto-refresh on 401.
- Idempotency via 'PayPal-Request-Id' header and local in-memory duplicate guard.
- Strict timeout enforcement and retry bounds.
- Sanitized errors hiding internal secrets.
"""

import uuid
import logging
from typing import Optional, Dict, Any
import httpx

from backend.paypal.config import (
    PAYPAL_API_BASE,
    PAYPAL_TIMEOUT_SECONDS,
    PAYPAL_MAX_RETRIES,
)
from backend.paypal.auth import (
    get_auth_manager,
    PayPalAuthError,
    PayPalNotConfiguredError,
)

logger = logging.getLogger("paytriage.paypal.client")


class PayPalClientError(Exception):
    """Base exception for PayPal client failures."""
    pass


class PayPalApiError(PayPalClientError):
    """Raised when PayPal returns a non-2xx status code."""
    def __init__(self, message: str, status_code: int, error_name: Optional[str] = None, details: Optional[Any] = None):
        super().__init__(message)
        self.status_code = status_code
        self.error_name = error_name
        self.details = details


class PayPalNotFoundError(PayPalApiError):
    """Raised when an invoice or resource does not exist (HTTP 404)."""
    pass


class PayPalRateLimitError(PayPalApiError):
    """Raised when PayPal rate limits requests (HTTP 429)."""
    pass


class PayPalTimeoutError(PayPalClientError):
    """Raised when request to PayPal exceeds timeout."""
    pass


class PayPalNetworkError(PayPalClientError):
    """Raised when network transport fails."""
    pass


class PayPalDuplicateRequestError(PayPalClientError):
    """Raised by local duplicate guard when identical operation is submitted concurrently."""
    pass


class PayPalClient:
    """HTTP Client for PayPal REST Invoicing V2 API."""

    def __init__(self, http_client: Optional[httpx.Client] = None):
        self._http = http_client or httpx.Client(timeout=PAYPAL_TIMEOUT_SECONDS)
        self._processed_request_ids = set()

    def request(
        self,
        method: str,
        path: str,
        json_data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute authenticated request against PayPal API with idempotency and retry guards."""
        # Local duplicate guard on POST/PUT requests
        if method.upper() in ("POST", "PUT") and request_id:
            if request_id in self._processed_request_ids:
                raise PayPalDuplicateRequestError(
                    f"Duplicate request detected locally: request_id '{request_id}' has already been processed."
                )

        url = f"{PAYPAL_API_BASE}{path}"
        auth_mgr = get_auth_manager()

        for attempt in range(1, PAYPAL_MAX_RETRIES + 2):
            token = auth_mgr.get_access_token(client=self._http)
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
            if request_id:
                headers["PayPal-Request-Id"] = request_id

            logger.info(f"Dispatching PayPal API request: {method.upper()} {path} (attempt {attempt})")

            try:
                resp = self._http.request(
                    method=method.upper(),
                    url=url,
                    headers=headers,
                    json=json_data,
                    params=params,
                )

                # Handle token expiry / 401
                if resp.status_code == 401 and attempt == 1:
                    logger.warning("PayPal token rejected with 401. Clearing token cache and refreshing...")
                    auth_mgr.clear_cache()
                    continue

                return self._handle_response(resp, request_id)

            except (httpx.TimeoutException, TimeoutError) as te:
                logger.error(f"PayPal request timed out: {te}")
                raise PayPalTimeoutError(f"PayPal request to {path} timed out after {PAYPAL_TIMEOUT_SECONDS}s.")
            except httpx.RequestError as re:
                logger.error(f"PayPal network error: {re}")
                raise PayPalNetworkError(f"Network transport error contacting PayPal: {re}")

        raise PayPalApiError("Max authentication retries exhausted.", status_code=401)

    def _handle_response(self, resp: httpx.Response, request_id: Optional[str] = None) -> Dict[str, Any]:
        """Parse response payload, map HTTP errors, and record idempotency."""
        code = resp.status_code

        # 204 No Content
        if code == 204:
            if request_id:
                self._processed_request_ids.add(request_id)
            return {"status": "success", "http_status": 204}

        # Safe JSON parse
        try:
            body = resp.json() if resp.text else {}
        except Exception:
            body = {"raw_text": resp.text[:200]}

        if 200 <= code < 300:
            if request_id:
                self._processed_request_ids.add(request_id)
            return body

        # Error handling
        err_name = body.get("name") if isinstance(body, dict) else None
        err_msg = body.get("message") if isinstance(body, dict) else resp.text[:200]
        details = body.get("details") if isinstance(body, dict) else None

        clean_message = f"PayPal API Error (HTTP {code}): {err_name or 'Request Failed'} — {err_msg}"

        if code == 404:
            raise PayPalNotFoundError(clean_message, status_code=404, error_name=err_name, details=details)
        elif code == 429:
            raise PayPalRateLimitError(clean_message, status_code=429, error_name=err_name, details=details)
        else:
            raise PayPalApiError(clean_message, status_code=code, error_name=err_name, details=details)

