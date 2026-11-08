"""
PayTriage — PayPal Sandbox Integration Package
Conforms strictly to phase4.md and RULES.md (§8, §9).
"""

from backend.paypal.config import (
    is_paypal_configured,
    get_paypal_client_id,
    get_paypal_client_secret,
    PAYPAL_MODE,
    PAYPAL_API_BASE,
)
from backend.paypal.auth import (
    PayPalAuthManager,
    PayPalAuthError,
    PayPalNotConfiguredError,
    get_auth_manager,
    get_paypal_access_token,
)
from backend.paypal.client import (
    PayPalClient,
    PayPalClientError,
    PayPalApiError,
    PayPalNotFoundError,
    PayPalRateLimitError,
    PayPalTimeoutError,
    PayPalNetworkError,
    PayPalDuplicateRequestError,
)
from backend.paypal.invoices import (
    create_sandbox_invoice,
    get_sandbox_invoice,
    map_paypal_status_to_app,
    sync_paypal_invoice,
    send_sandbox_invoice,
    remind_sandbox_invoice,
    verify_sandbox_invoice_payment,
)
from backend.paypal.router import router as paypal_router

__all__ = [
    "is_paypal_configured",
    "get_paypal_client_id",
    "get_paypal_client_secret",
    "PAYPAL_MODE",
    "PAYPAL_API_BASE",
    "PayPalAuthManager",
    "PayPalAuthError",
    "PayPalNotConfiguredError",
    "get_auth_manager",
    "get_paypal_access_token",
    "PayPalClient",
    "PayPalClientError",
    "PayPalApiError",
    "PayPalNotFoundError",
    "PayPalRateLimitError",
    "PayPalTimeoutError",
    "PayPalNetworkError",
    "PayPalDuplicateRequestError",
    "create_sandbox_invoice",
    "get_sandbox_invoice",
    "map_paypal_status_to_app",
    "sync_paypal_invoice",
    "send_sandbox_invoice",
    "remind_sandbox_invoice",
    "verify_sandbox_invoice_payment",
    "paypal_router",
]

