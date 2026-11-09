"""
PayTriage — PayPal Sandbox Integration Package
Conforms strictly to phase4.md and RULES.md (§8, §9).
"""

from backend.paypal.auth import (
    PayPalAuthError,
    PayPalAuthManager,
    PayPalNotConfiguredError,
    get_auth_manager,
    get_paypal_access_token,
)
from backend.paypal.client import (
    PayPalApiError,
    PayPalClient,
    PayPalClientError,
    PayPalDuplicateRequestError,
    PayPalNetworkError,
    PayPalNotFoundError,
    PayPalRateLimitError,
    PayPalTimeoutError,
)
from backend.paypal.config import (
    PAYPAL_API_BASE,
    PAYPAL_MODE,
    get_paypal_client_id,
    get_paypal_client_secret,
    is_paypal_configured,
)
from backend.paypal.invoices import (
    create_sandbox_invoice,
    get_sandbox_invoice,
    map_paypal_status_to_app,
    remind_sandbox_invoice,
    send_sandbox_invoice,
    sync_paypal_invoice,
    verify_sandbox_invoice_payment,
)
from backend.paypal.router import router as paypal_router

__all__ = [
    "PAYPAL_API_BASE",
    "PAYPAL_MODE",
    "PayPalApiError",
    "PayPalAuthError",
    "PayPalAuthManager",
    "PayPalClient",
    "PayPalClientError",
    "PayPalDuplicateRequestError",
    "PayPalNetworkError",
    "PayPalNotConfiguredError",
    "PayPalNotFoundError",
    "PayPalRateLimitError",
    "PayPalTimeoutError",
    "create_sandbox_invoice",
    "get_auth_manager",
    "get_paypal_access_token",
    "get_paypal_client_id",
    "get_paypal_client_secret",
    "get_sandbox_invoice",
    "is_paypal_configured",
    "map_paypal_status_to_app",
    "paypal_router",
    "remind_sandbox_invoice",
    "send_sandbox_invoice",
    "sync_paypal_invoice",
    "verify_sandbox_invoice_payment",
]

