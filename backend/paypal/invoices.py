"""
PayTriage PayPal — Invoice Lifecycle Operations, Sync, and Payment Verification
Strictly conforms to phase4.md (Steps 2-6) and RULES.md (§8, §9).
Operations:
- Step 2: Create draft invoice in PayPal Sandbox (POST /v2/invoicing/invoices)
- Step 3: Fetch invoice details (GET /v2/invoicing/invoices/{id}) & status mapping
- Step 4: Synchronize PayPal invoice data into PayTriage SQLite database
- Step 5: Execute supported operations (send, remind)
- Step 6: Payment verification and audit logging
"""

import uuid
import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Dict, Any, Optional

from backend.database import (
    insert_invoice,
    get_invoice_by_id,
    log_activity,
)
from backend.paypal.client import PayPalClient
from backend.paypal.schemas import (
    PayPalInvoiceResponse,
    CreateInvoicePayload,
    InvoiceDetailInput,
    RecipientInfo,
    RecipientBillingInfo,
    ParticipantName,
    InvoiceLineItem,
    MoneyAmount,
    PayPalSyncResult,
)

logger = logging.getLogger("paytriage.paypal.invoices")


def map_paypal_status_to_app(
    paypal_status: str,
    due_date: Optional[date] = None,
    today: Optional[date] = None,
) -> str:
    """Map official PayPal Invoicing V2 statuses to PayTriage internal statuses.
    
    Status mapping table:
    | PayPal Status        | Due Date Condition | PayTriage Status | Actionability                 |
    |----------------------|--------------------|------------------|-------------------------------|
    | DRAFT                | Any                | DRAFT            | Excluded from recovery score  |
    | SCHEDULED            | Any                | DRAFT            | Awaiting dispatch             |
    | SENT / UNPAID        | days_overdue > 0   | OVERDUE          | Actionable in recovery queue  |
    | SENT / UNPAID        | days_overdue <= 0  | SENT             | Not yet overdue               |
    | PARTIALLY_PAID       | Any                | PARTIALLY_PAID   | Actionable in recovery queue  |
    | PAID                 | Any                | PAID             | Terminal (no recovery needed) |
    | MARKED_AS_PAID       | Any                | PAID             | Terminal (verified external)  |
    | CANCELLED            | Any                | CANCELLED        | Terminal                      |
    | REFUNDED             | Any                | REFUNDED         | Terminal                      |
    | PARTIALLY_REFUNDED   | Any                | REFUNDED         | Terminal                      |
    | PAYMENT_PENDING      | days_overdue > 0   | OVERDUE          | Pending clearance             |
    | PAYMENT_PENDING      | days_overdue <= 0  | SENT             | Pending clearance             |
    """
    clean_status = (paypal_status or "").upper().strip()
    eval_today = today or date.today()

    if clean_status in ("DRAFT", "SCHEDULED"):
        return "DRAFT"

    if clean_status in ("PAID", "MARKED_AS_PAID"):
        return "PAID"

    if clean_status in ("CANCELLED",):
        return "CANCELLED"

    if clean_status in ("REFUNDED", "PARTIALLY_REFUNDED", "MARKED_AS_REFUNDED"):
        return "REFUNDED"

    if clean_status == "PARTIALLY_PAID":
        return "PARTIALLY_PAID"

    if clean_status in ("SENT", "UNPAID", "PAYMENT_PENDING"):
        if due_date and (eval_today - due_date).days > 0:
            return "OVERDUE"
        return "SENT"

    # Default fallback
    if due_date and (eval_today - due_date).days > 0:
        return "OVERDUE"
    return "SENT"


def create_sandbox_invoice(
    invoice_data: Dict[str, Any],
    request_id: Optional[str] = None,
    client: Optional[PayPalClient] = None,
) -> PayPalInvoiceResponse:
    """Create a draft invoice in PayPal Sandbox per official v2 schema.
    Endpoint: POST /v2/invoicing/invoices
    """
    http_client = client or PayPalClient()
    req_id = request_id or str(uuid.uuid4())

    inv_num = invoice_data.get("invoice_number", f"INV-{uuid.uuid4().hex[:8].upper()}")
    inv_date = str(invoice_data.get("invoice_date", date.today().isoformat()))
    due_date = str(invoice_data.get("due_date", date.today().isoformat()))
    currency = invoice_data.get("currency", "USD")
    total_val = f"{float(invoice_data.get('total_amount', '100.00')):.2f}"

    # Build schema payload
    payload = CreateInvoicePayload(
        detail=InvoiceDetailInput(
            invoice_number=inv_num,
            invoice_date=inv_date,
            currency_code=currency,
            note=invoice_data.get("notes"),
        ),
        primary_recipients=[
            RecipientInfo(
                billing_info=RecipientBillingInfo(
                    name=ParticipantName(
                        full_name=invoice_data.get("customer_name", "Valued Customer"),
                    ),
                    email_address=invoice_data.get("customer_email", "customer@example.com"),
                )
            )
        ],
        items=[
            InvoiceLineItem(
                name=invoice_data.get("item_name", "Professional Services"),
                description=invoice_data.get("item_description", "Accounts Receivable Recovery"),
                quantity="1",
                unit_amount=MoneyAmount(
                    currency_code=currency,
                    value=total_val,
                ),
            )
        ],
    )

    resp_json = http_client.request(
        method="POST",
        path="/v2/invoicing/invoices",
        json_data=payload.model_dump(exclude_none=True),
        request_id=req_id,
    )

    # In PayPal Invoicing V2 API, POST /v2/invoicing/invoices returns a HATEOAS link:
    # {"rel": "self", "href": "https://api-m.sandbox.paypal.com/v2/invoicing/invoices/{id}", "method": "GET"}
    # or the full invoice object.
    inv_id = resp_json.get("id")
    if not inv_id and "href" in resp_json:
        inv_id = resp_json["href"].rstrip("/").split("/")[-1]

    if not inv_id:
        raise PayPalApiError(f"PayPal did not return an invoice ID or href in creation response: {resp_json}", status_code=201)

    # If the response only contained the link (no status field), fetch the full invoice
    if "status" not in resp_json:
        parsed = get_sandbox_invoice(inv_id, client=http_client)
    else:
        parsed = PayPalInvoiceResponse.model_validate(resp_json)

    logger.info(f"Created PayPal Sandbox draft invoice: {parsed.id} (status={parsed.status})")
    return parsed


def get_sandbox_invoice(
    invoice_id: str,
    client: Optional[PayPalClient] = None,
) -> PayPalInvoiceResponse:
    """Retrieve full details of an invoice from PayPal Sandbox.
    Endpoint: GET /v2/invoicing/invoices/{invoice_id}
    """
    http_client = client or PayPalClient()
    resp_json = http_client.request(
        method="GET",
        path=f"/v2/invoicing/invoices/{invoice_id}",
    )
    return PayPalInvoiceResponse.model_validate(resp_json)


def sync_paypal_invoice(
    invoice_id: str,
    today: Optional[date] = None,
    client: Optional[PayPalClient] = None,
) -> PayPalSyncResult:
    """Synchronize an invoice from PayPal Sandbox into the PayTriage SQLite database.
    Strictly adheres to RULES.md §4: Never marks paid without PayPal evidence.
    """
    eval_today = today or date.today()
    live_inv = get_sandbox_invoice(invoice_id, client=client)

    # 1. Extract and compute amounts
    total_val = Decimal("0.00")
    if live_inv.amount and live_inv.amount.value:
        total_val = Decimal(str(live_inv.amount.value))

    due_val = total_val
    if live_inv.due_amount and live_inv.due_amount.value:
        due_val = Decimal(str(live_inv.due_amount.value))

    # 2. Extract due date
    due_date = eval_today
    if live_inv.detail and live_inv.detail.payment_term and "due_date" in live_inv.detail.payment_term:
        raw_due = live_inv.detail.payment_term["due_date"]
        due_date = date.fromisoformat(raw_due) if isinstance(raw_due, str) else raw_due

    # 3. Determine verified payment evidence
    is_paid = False
    evidence_source = "none"
    paypal_status = live_inv.status.upper()

    if paypal_status in ("PAID", "MARKED_AS_PAID"):
        is_paid = True
        evidence_source = f"paypal_status:{paypal_status}"
    elif live_inv.payments and live_inv.payments.paid_amount and live_inv.payments.paid_amount.value:
        paid_val = Decimal(str(live_inv.payments.paid_amount.value))
        if paid_val >= total_val and total_val > 0:
            is_paid = True
            evidence_source = "paypal_payments_summary"
            due_val = Decimal("0.00")

    # 4. Map to application status
    if is_paid:
        app_status = "PAID"
    else:
        app_status = map_paypal_status_to_app(paypal_status, due_date=due_date, today=eval_today)

    # 5. Extract recipient metadata safely
    cust_name = "Customer"
    cust_email = None
    if live_inv.primary_recipients and len(live_inv.primary_recipients) > 0:
        recip = live_inv.primary_recipients[0]
        billing = recip.get("billing_info", {})
        cust_email = billing.get("email_address")
        name_obj = billing.get("name", {})
        cust_name = name_obj.get("full_name") or name_obj.get("given_name") or "Customer"

    inv_num = (live_inv.detail.invoice_number if live_inv.detail and live_inv.detail.invoice_number else live_inv.id)
    currency = live_inv.amount.currency_code if live_inv.amount and live_inv.amount.currency_code else "USD"

    # Check existing DB record to preserve reminder count & history
    existing = get_invoice_by_id(live_inv.id)
    reminder_count = existing["reminder_count"] if existing else 0
    last_reminder = existing.get("last_reminder_date") if existing else None
    payment_history = existing.get("payment_history") if existing else None

    # Upsert into PayTriage database
    db_record = {
        "id": live_inv.id,
        "invoice_number": inv_num,
        "customer_name": cust_name,
        "customer_email": cust_email,
        "total_amount": str(total_val),
        "outstanding_amount": str(due_val),
        "currency": currency,
        "status": app_status,
        "due_date": due_date,
        "reminder_count": reminder_count,
        "last_reminder_date": last_reminder,
        "payment_history": payment_history,
        "has_promise_to_pay": False,
        "promise_due_date": None,
        "notes": f"Synced from PayPal Sandbox ({live_inv.id})",
        "is_demo": False,
    }
    insert_invoice(db_record)

    now_iso = datetime.now().isoformat()
    log_activity(
        invoice_id=live_inv.id,
        action_type="paypal_sync",
        status="success",
        details=f"Synced PayPal invoice {live_inv.id}: status={app_status}, due={due_val} {currency} (evidence: {evidence_source}).",
    )

    return PayPalSyncResult(
        paypal_invoice_id=live_inv.id,
        app_invoice_id=live_inv.id,
        paypal_status=paypal_status,
        app_status=app_status,
        total_amount=total_val,
        outstanding_amount=due_val,
        currency=currency,
        is_paid_verified=is_paid,
        evidence_source=evidence_source,
        synced_at=now_iso,
        action_recorded="invoice_upserted",
    )


def send_sandbox_invoice(
    invoice_id: str,
    send_to_recipient: bool = True,
    request_id: Optional[str] = None,
    client: Optional[PayPalClient] = None,
) -> Dict[str, Any]:
    """Execute supported invoice operation: Send invoice to recipient via PayPal.
    Endpoint: POST /v2/invoicing/invoices/{invoice_id}/send
    """
    http_client = client or PayPalClient()
    req_id = request_id or str(uuid.uuid4())

    body = {"send_to_recipient": send_to_recipient, "send_to_invoicer": False}

    res = http_client.request(
        method="POST",
        path=f"/v2/invoicing/invoices/{invoice_id}/send",
        json_data=body,
        request_id=req_id,
    )

    log_activity(
        invoice_id=invoice_id,
        action_type="paypal_send",
        status="success",
        details=f"Dispatched official PayPal invoice send operation (request_id={req_id}).",
    )
    return res


def remind_sandbox_invoice(
    invoice_id: str,
    note: Optional[str] = None,
    send_to_recipient: bool = True,
    request_id: Optional[str] = None,
    client: Optional[PayPalClient] = None,
) -> Dict[str, Any]:
    """Execute supported invoice operation: Send payment reminder to payer.
    Endpoint: POST /v2/invoicing/invoices/{invoice_id}/remind
    Note per official docs: Maximum 2 reminders per day allowed by PayPal.
    """
    http_client = client or PayPalClient()
    req_id = request_id or str(uuid.uuid4())

    body = {
        "send_to_recipient": send_to_recipient,
        "send_to_invoicer": False,
    }
    if note and str(note).strip():
        body["note"] = str(note).strip()

    res = http_client.request(
        method="POST",
        path=f"/v2/invoicing/invoices/{invoice_id}/remind",
        json_data=body,
        request_id=req_id,
    )

    log_activity(
        invoice_id=invoice_id,
        action_type="paypal_remind",
        status="success",
        details=f"Dispatched official PayPal reminder transmission (request_id={req_id}).",
    )
    return res


def verify_sandbox_invoice_payment(
    invoice_id: str,
    client: Optional[PayPalClient] = None,
) -> Dict[str, Any]:
    """Re-fetch invoice from PayPal after an operation and record verified state.
    Strictly conforms to phase4.md Step 6.
    """
    sync_res = sync_paypal_invoice(invoice_id=invoice_id, client=client)

    log_activity(
        invoice_id=invoice_id,
        action_type="paypal_payment_verification",
        status="verified" if sync_res.is_paid_verified else "unpaid",
        details=(
            f"Payment verified: {sync_res.is_paid_verified}. "
            f"Current status: {sync_res.app_status}, outstanding: {sync_res.currency} {sync_res.outstanding_amount}."
        ),
    )

    return {
        "invoice_id": invoice_id,
        "is_paid": sync_res.is_paid_verified,
        "status": sync_res.app_status,
        "outstanding_amount": str(sync_res.outstanding_amount),
        "currency": sync_res.currency,
        "verified_at": datetime.now().isoformat(),
    }

