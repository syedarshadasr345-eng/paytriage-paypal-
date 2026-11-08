"""
PayTriage PayPal — Safe Setup & Status Router
Strictly conforms to phase4.md and RULES.md (§8).
Exposes setup status only. PayPal consequential operations remain protected service functions.
"""

from fastapi import APIRouter

from backend.paypal.config import (
    is_paypal_configured,
    PAYPAL_MODE,
    PAYPAL_API_BASE,
    get_paypal_client_id,
    mask_credential,
)
from backend.paypal.schemas import PayPalStatusResponse

router = APIRouter(prefix="/api/paypal", tags=["paypal"])


@router.get("/status", response_model=PayPalStatusResponse)
def get_paypal_sandbox_status():
    """Report safe PayPal Sandbox setup state. Never pretends to be connected if credentials are missing."""
    configured = is_paypal_configured()
    client_id = get_paypal_client_id()

    if configured:
        return PayPalStatusResponse(
            configured=True,
            mode=PAYPAL_MODE,
            api_base=PAYPAL_API_BASE,
            status_label="ready",
            client_id_preview=mask_credential(client_id),
            message="PayPal Sandbox integration is configured and ready.",
        )
    else:
        return PayPalStatusResponse(
            configured=False,
            mode=PAYPAL_MODE,
            api_base=PAYPAL_API_BASE,
            status_label="not_configured",
            client_id_preview="[NOT_SET]",
            message="PayPal Sandbox not configured. Set PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET in backend/.env.",
        )

