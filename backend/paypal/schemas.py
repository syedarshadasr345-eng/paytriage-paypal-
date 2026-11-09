"""
PayTriage PayPal — Pydantic Schemas for PayPal Invoicing V2 & OAuth
Strictly conforms to phase4.md and RULES.md (§8, §9).
Resilient schema design: unknown or unexpected fields from PayPal do not crash the app.
"""

from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# -----------------------------------------------------------------------------
# OAuth Schemas
# -----------------------------------------------------------------------------

class PayPalOAuthToken(BaseModel):
    """Token response from POST /v1/oauth2/token."""
    model_config = ConfigDict(extra="allow")

    access_token: str
    token_type: str = "Bearer"
    expires_in: int = 32400
    scope: str | None = None
    app_id: str | None = None
    nonce: str | None = None


class PayPalStatusResponse(BaseModel):
    """Safe status report for PayPal Sandbox connectivity and setup state."""
    model_config = ConfigDict(extra="ignore")

    configured: bool
    mode: str
    api_base: str
    status_label: Literal["ready", "not_configured"]
    client_id_preview: str
    message: str


# -----------------------------------------------------------------------------
# PayPal Invoicing V2 Creation Schemas
# -----------------------------------------------------------------------------

class MoneyAmount(BaseModel):
    model_config = ConfigDict(extra="allow")
    currency_code: str = "USD"
    value: str


class InvoicePaymentTerm(BaseModel):
    model_config = ConfigDict(extra="allow")
    term_type: str = "DUE_ON_DATE"
    due_date: str | None = None


class InvoiceDetailInput(BaseModel):
    model_config = ConfigDict(extra="allow")
    invoice_number: str
    invoice_date: str
    currency_code: str = "USD"
    note: str | None = None
    terms_and_conditions: str | None = None
    payment_term: InvoicePaymentTerm | None = None


class ParticipantName(BaseModel):
    model_config = ConfigDict(extra="allow")
    given_name: str | None = None
    surname: str | None = None
    business_name: str | None = None


class InvoicerInfo(BaseModel):
    model_config = ConfigDict(extra="allow")
    name: ParticipantName | None = None
    email_address: str


class RecipientBillingInfo(BaseModel):
    model_config = ConfigDict(extra="allow")
    name: ParticipantName | None = None
    email_address: str


class RecipientInfo(BaseModel):
    model_config = ConfigDict(extra="allow")
    billing_info: RecipientBillingInfo


class InvoiceLineItem(BaseModel):
    model_config = ConfigDict(extra="allow")
    name: str
    description: str | None = None
    quantity: str = "1"
    unit_amount: MoneyAmount


class CreateInvoicePayload(BaseModel):
    """Payload for POST /v2/invoicing/invoices per official PayPal V2 schema."""
    model_config = ConfigDict(extra="allow")

    detail: InvoiceDetailInput
    invoicer: InvoicerInfo | None = None
    primary_recipients: list[RecipientInfo]
    items: list[InvoiceLineItem]


# -----------------------------------------------------------------------------
# PayPal Invoicing V2 Read & Sync Schemas
# -----------------------------------------------------------------------------

class PayPalInvoiceDetailResponse(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str | None = None
    invoice_number: str | None = None
    invoice_date: str | None = None
    currency_code: str | None = None
    payment_term: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None


class PayPalAmountBreakdown(BaseModel):
    model_config = ConfigDict(extra="allow")
    currency_code: str | None = None
    value: str | None = None


class PayPalInvoiceAmount(BaseModel):
    model_config = ConfigDict(extra="allow")
    currency_code: str | None = None
    value: str | None = None
    breakdown: dict[str, Any] | None = None


class PayPalPaymentDetail(BaseModel):
    model_config = ConfigDict(extra="allow")
    paid_amount: PayPalAmountBreakdown | None = None
    payment_date: str | None = None
    method: str | None = None
    type: str | None = None
    note: str | None = None


class PayPalPaymentsSummary(BaseModel):
    model_config = ConfigDict(extra="allow")
    paid_amount: PayPalAmountBreakdown | None = None
    transactions: list[dict[str, Any]] | None = Field(default_factory=list)


class PayPalInvoiceResponse(BaseModel):
    """Complete invoice model from GET /v2/invoicing/invoices/{id}."""
    model_config = ConfigDict(extra="allow")

    id: str
    status: str
    detail: PayPalInvoiceDetailResponse | None = None
    invoicer: dict[str, Any] | None = None
    primary_recipients: list[dict[str, Any]] | None = None
    items: list[dict[str, Any]] | None = None
    amount: PayPalInvoiceAmount | None = None
    due_amount: PayPalAmountBreakdown | None = None
    payments: PayPalPaymentsSummary | None = None
    links: list[dict[str, Any]] | None = None


class PayPalSyncResult(BaseModel):
    """Summary of syncing a PayPal Sandbox invoice into PayTriage SQLite."""
    model_config = ConfigDict(extra="ignore")

    paypal_invoice_id: str
    app_invoice_id: str
    paypal_status: str
    app_status: str
    total_amount: Decimal
    outstanding_amount: Decimal
    currency: str
    is_paid_verified: bool
    evidence_source: str
    synced_at: str
    action_recorded: str

