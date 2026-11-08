"""
PayTriage PayPal — Pydantic Schemas for PayPal Invoicing V2 & OAuth
Strictly conforms to phase4.md and RULES.md (§8, §9).
Resilient schema design: unknown or unexpected fields from PayPal do not crash the app.
"""

from typing import List, Optional, Dict, Any, Literal
from decimal import Decimal
from pydantic import BaseModel, Field, ConfigDict


# -----------------------------------------------------------------------------
# OAuth Schemas
# -----------------------------------------------------------------------------

class PayPalOAuthToken(BaseModel):
    """Token response from POST /v1/oauth2/token."""
    model_config = ConfigDict(extra="allow")

    access_token: str
    token_type: str = "Bearer"
    expires_in: int = 32400
    scope: Optional[str] = None
    app_id: Optional[str] = None
    nonce: Optional[str] = None


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
    due_date: Optional[str] = None


class InvoiceDetailInput(BaseModel):
    model_config = ConfigDict(extra="allow")
    invoice_number: str
    invoice_date: str
    currency_code: str = "USD"
    note: Optional[str] = None
    terms_and_conditions: Optional[str] = None
    payment_term: Optional[InvoicePaymentTerm] = None


class ParticipantName(BaseModel):
    model_config = ConfigDict(extra="allow")
    given_name: Optional[str] = None
    surname: Optional[str] = None
    business_name: Optional[str] = None


class InvoicerInfo(BaseModel):
    model_config = ConfigDict(extra="allow")
    name: Optional[ParticipantName] = None
    email_address: str


class RecipientBillingInfo(BaseModel):
    model_config = ConfigDict(extra="allow")
    name: Optional[ParticipantName] = None
    email_address: str


class RecipientInfo(BaseModel):
    model_config = ConfigDict(extra="allow")
    billing_info: RecipientBillingInfo


class InvoiceLineItem(BaseModel):
    model_config = ConfigDict(extra="allow")
    name: str
    description: Optional[str] = None
    quantity: str = "1"
    unit_amount: MoneyAmount


class CreateInvoicePayload(BaseModel):
    """Payload for POST /v2/invoicing/invoices per official PayPal V2 schema."""
    model_config = ConfigDict(extra="allow")

    detail: InvoiceDetailInput
    invoicer: Optional[InvoicerInfo] = None
    primary_recipients: List[RecipientInfo]
    items: List[InvoiceLineItem]


# -----------------------------------------------------------------------------
# PayPal Invoicing V2 Read & Sync Schemas
# -----------------------------------------------------------------------------

class PayPalInvoiceDetailResponse(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: Optional[str] = None
    invoice_number: Optional[str] = None
    invoice_date: Optional[str] = None
    currency_code: Optional[str] = None
    payment_term: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None


class PayPalAmountBreakdown(BaseModel):
    model_config = ConfigDict(extra="allow")
    currency_code: Optional[str] = None
    value: Optional[str] = None


class PayPalInvoiceAmount(BaseModel):
    model_config = ConfigDict(extra="allow")
    currency_code: Optional[str] = None
    value: Optional[str] = None
    breakdown: Optional[Dict[str, Any]] = None


class PayPalPaymentDetail(BaseModel):
    model_config = ConfigDict(extra="allow")
    paid_amount: Optional[PayPalAmountBreakdown] = None
    payment_date: Optional[str] = None
    method: Optional[str] = None
    type: Optional[str] = None
    note: Optional[str] = None


class PayPalPaymentsSummary(BaseModel):
    model_config = ConfigDict(extra="allow")
    paid_amount: Optional[PayPalAmountBreakdown] = None
    transactions: Optional[List[Dict[str, Any]]] = Field(default_factory=list)


class PayPalInvoiceResponse(BaseModel):
    """Complete invoice model from GET /v2/invoicing/invoices/{id}."""
    model_config = ConfigDict(extra="allow")

    id: str
    status: str
    detail: Optional[PayPalInvoiceDetailResponse] = None
    invoicer: Optional[Dict[str, Any]] = None
    primary_recipients: Optional[List[Dict[str, Any]]] = None
    items: Optional[List[Dict[str, Any]]] = None
    amount: Optional[PayPalInvoiceAmount] = None
    due_amount: Optional[PayPalAmountBreakdown] = None
    payments: Optional[PayPalPaymentsSummary] = None
    links: Optional[List[Dict[str, Any]]] = None


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

