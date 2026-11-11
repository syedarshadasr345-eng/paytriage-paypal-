# PayTriage — PayPal Invoicing V2 Integration Architecture

## 1. Overview & Operational Principles

PayTriage integrates with the official **PayPal Invoicing V2 REST API** (`api-m.sandbox.paypal.com`) to provide genuine invoice lifecycle management, payment status verification, and outreach synchronization.

### Strict Guarantees:
1. **Never Mark Paid Without Evidence**: An invoice is marked `PAID` if and only if PayPal returns an explicit terminal payment state (`status == 'PAID'` or `status == 'MARKED_AS_PAID'`) or verified transaction evidence in `payments.paid_amount >= total_amount`.
2. **Idempotency & Replay Defense**: All mutation requests (`POST`, `PUT`) pass a unique `PayPal-Request-Id` HTTP header. A local in-memory duplicate guard prevents re-transmissions.
3. **Sandbox Isolation**: Only the sandbox endpoint (`https://api-m.sandbox.paypal.com`) is contacted. Live production credentials are unconditionally disallowed.
4. **Approval Gate Isolation**: In Phase 4, PayPal operations are accessible only as backend service functions and automated verification scripts. They are **not** exposed to the frontend UI or AI assistant until Phase 5 merchant review is implemented.

---

## 2. Status Mapping Table

Official PayPal Invoicing V2 statuses are mapped deterministically to PayTriage internal states based on verified PayPal data and due date aging:

| PayPal V2 Status | Due Date Condition | PayTriage Status | Queue Actionability | Description |
|---|---|---|---|---|
| `DRAFT` | Any | `DRAFT` | Excluded | Draft created; not yet finalized or sent |
| `SCHEDULED` | Any | `DRAFT` | Excluded | Scheduled for future dispatch |
| `SENT` | `days_overdue <= 0` | `SENT` | Excluded (by default) | Sent to customer; not yet due |
| `SENT` | `days_overdue > 0` | `OVERDUE` | **Actionable** | Active overdue invoice eligible for recovery |
| `UNPAID` | `days_overdue <= 0` | `SENT` | Excluded (by default) | Awaiting settlement |
| `UNPAID` | `days_overdue > 0` | `OVERDUE` | **Actionable** | Overdue settlement eligible for recovery |
| `PARTIALLY_PAID` | Any | `PARTIALLY_PAID` | **Actionable** | Partial remittance recorded; remainder due |
| `PAYMENT_PENDING` | `days_overdue <= 0` | `SENT` | Excluded | Payment processing / bank clearance |
| `PAYMENT_PENDING` | `days_overdue > 0` | `OVERDUE` | **Actionable** | Clearance pending past maturity |
| `PAID` | Any | `PAID` | Excluded (Terminal) | Verified full settlement |
| `MARKED_AS_PAID` | Any | `PAID` | Excluded (Terminal) | Verified external offline settlement |
| `CANCELLED` | Any | `CANCELLED` | Excluded (Terminal) | Voided / cancelled by merchant |
| `REFUNDED` | Any | `REFUNDED` | Excluded (Terminal) | Remittance refunded |
| `PARTIALLY_REFUNDED`| Any | `REFUNDED` | Excluded (Terminal) | Remittance partially refunded |

---

## 3. Supported PayPal Endpoints & Workflows

### A. Authentication
- **Endpoint**: `POST /v1/oauth2/token`
- **Method**: HTTP Basic Authentication (`client_id:client_secret`) with `grant_type=client_credentials`.
- **Token Cache**: Cached in-memory with proactive refresh 60 seconds prior to expiration (`expires_in - 60s`).

### B. Draft Invoice Creation
- **Endpoint**: `POST /v2/invoicing/invoices`
- **Payload**: Full v2 schema with `detail`, `primary_recipients`, and `items`.
- **Response**: Returns HTTP 201 with HATEOAS link (`rel="self"`, `href=".../invoices/{id}"`) or full invoice entity. PayTriage safely resolves the ID from either format and queries verified state.

### C. Invoice Detail & Status Fetch
- **Endpoint**: `GET /v2/invoicing/invoices/{invoice_id}`
- **Validation**: Pydantic models with `model_config = ConfigDict(extra="allow")` ensure unknown fields returned by PayPal never crash the application.

### D. Invoice Dispatch (Send)
- **Endpoint**: `POST /v2/invoicing/invoices/{invoice_id}/send`
- **Payload**: `{"send_to_recipient": true, "send_to_invoicer": false}`
- **Effect**: Transitions invoice status from `DRAFT` to `SENT` and returns payer-view URL (`https://www.sandbox.paypal.com/invoice/p/#{id}`).

### E. Payment Reminder Dispatch (Remind)
- **Endpoint**: `POST /v2/invoicing/invoices/{invoice_id}/remind`
- **Payload**: Optional `{"note": "...", "send_to_recipient": true}`
- **Constraint**: Documented limit of at most 2 reminders per day per invoice enforced by PayPal.

### F. Payment Verification & Audit Logging
- Re-fetches the latest invoice state after every transmission.
- Writes an immutable record to SQLite `activity_logs` with `action_type="paypal_payment_verification"`.

---

## 4. Live Sandbox Evidence

Live test run completed on 2026-11-08:
- **Sandbox Base URL**: `https://api-m.sandbox.paypal.com`
- **Client ID**: Configured in backend/.env (verified Indian developer account)
- **Created Invoice ID**: `INV2-7KYA-LFY4-CL67-Q5N6`
- **Initial Status**: `DRAFT` ($250.00 USD)
- **Sent Status**: `SENT` (payer-view URL generated: `https://www.sandbox.paypal.com/invoice/p/#INV2-7KYA-LFY4-CL67-Q5N6`)
- **Verified State**: Database record synchronized with `is_demo=False`, `status="SENT"`, `outstanding_amount="250.00"`.

