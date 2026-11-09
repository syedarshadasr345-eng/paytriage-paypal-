"""
PayTriage PayPal — Comprehensive Live Sandbox Verification Script
Tests steps 3b through 3g live against PayPal Sandbox API:
3b. Create one invoice in Sandbox. Report invoice ID.
3c. Fetch invoice status and validate with Pydantic.
3d. Map status to app status.
3e. Sync into SQLite invoices table without corrupting seed data.
3f. Supported operation (send/remind). Record real PayPal response.
3g. Re-fetch and record verified state.
"""

import json
import sys
import time
from datetime import date, timedelta
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

from backend.database import get_invoice_by_id
from backend.paypal.client import PayPalApiError
from backend.paypal.config import (
    get_paypal_client_id,
    is_paypal_configured,
    mask_credential,
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


def run_live_test():
    print("=" * 70)
    print("PayTriage PayPal Sandbox Live Verification (Steps 3b - 3g)")
    print("=" * 70)
    print(f"PayPal Configured: {is_paypal_configured()}")
    print(f"Client ID:         {mask_credential(get_paypal_client_id())}")
    print()

    if not is_paypal_configured():
        print("[BLOCKED] PayPal credentials not configured in backend/.env")
        return

    # -------------------------------------------------------------------------
    # STEP 3b: Create Invoice in Sandbox
    # -------------------------------------------------------------------------
    print("STEP 3b: Creating draft invoice in PayPal Sandbox...")
    test_inv_payload = {
        "invoice_number": f"INV-SBX-{int(time.time())}",
        "customer_name": "Acme Live Sandbox Tester",
        "customer_email": "tester-buyer@example.com",
        "total_amount": "250.00",
        "currency": "USD",
        "due_date": (date.today() + timedelta(days=14)).isoformat(),
        "notes": "Live test invoice created by PayTriage Phase 4 automated suite.",
        "item_name": "Software Engineering Consultation",
        "item_description": "API Integration and System Recovery",
    }

    created_inv = None
    try:
        created_inv = create_sandbox_invoice(test_inv_payload)
        print("  [SUCCESS] Invoice created in PayPal Sandbox:")
        print(f"    Invoice ID:     {created_inv.id}")
        print(f"    Status:         {created_inv.status}")
        print(f"    Invoice Number: {created_inv.detail.invoice_number if created_inv.detail else 'N/A'}")
        if created_inv.amount:
            print(f"    Amount:         {created_inv.amount.currency_code} {created_inv.amount.value}")
    except PayPalApiError as e:
        print(f"  [ERROR] PayPal API returned error during creation (HTTP {e.status_code}):")
        print(f"    Name:    {e.error_name}")
        print(f"    Message: {e}")
        print(f"    Details: {json.dumps(e.details, indent=2) if e.details else 'None'}")
        return
    except Exception as e:
        print(f"  [ERROR] Creation failed: {e}")
        return

    invoice_id = created_inv.id

    # -------------------------------------------------------------------------
    # STEP 3c: Fetch Invoice Status & Validate with Pydantic
    # -------------------------------------------------------------------------
    print("\nSTEP 3c: Fetching invoice status from PayPal Sandbox...")
    try:
        fetched_inv = get_sandbox_invoice(invoice_id)
        print("  [SUCCESS] Fetched invoice response successfully validated with Pydantic:")
        print(f"    ID:     {fetched_inv.id}")
        print(f"    Status: {fetched_inv.status}")
        if fetched_inv.amount:
            print(f"    Total:  {fetched_inv.amount.currency_code} {fetched_inv.amount.value}")
        if fetched_inv.due_amount:
            print(f"    Due:    {fetched_inv.due_amount.currency_code} {fetched_inv.due_amount.value}")
    except Exception as e:
        print(f"  [ERROR] Fetching invoice failed: {e}")
        return

    # -------------------------------------------------------------------------
    # STEP 3d: Map PayPal Status to App Status
    # -------------------------------------------------------------------------
    print("\nSTEP 3d: Status mapping...")
    app_status = map_paypal_status_to_app(fetched_inv.status, due_date=date.today() + timedelta(days=14))
    print(f"  PayPal Status '{fetched_inv.status}' -> PayTriage Status '{app_status}'")

    # -------------------------------------------------------------------------
    # STEP 3e: Sync into SQLite Invoices Table
    # -------------------------------------------------------------------------
    print("\nSTEP 3e: Synchronizing into SQLite database...")
    try:
        sync_res = sync_paypal_invoice(invoice_id)
        print("  [SUCCESS] Synced into SQLite:")
        print(f"    App Invoice ID:     {sync_res.app_invoice_id}")
        print(f"    App Status:         {sync_res.app_status}")
        print(f"    Outstanding Amount: {sync_res.currency} {sync_res.outstanding_amount}")
        print(f"    Is Paid Verified:   {sync_res.is_paid_verified} (evidence: {sync_res.evidence_source})")
        print(f"    Synced At:          {sync_res.synced_at}")

        db_check = get_invoice_by_id(invoice_id)
        assert db_check is not None, "Synced invoice not found in DB!"
        assert db_check["id"] == invoice_id
        assert db_check["is_demo"] is False, "Synced PayPal invoice must be flagged is_demo=False!"
        print(f"  Verified DB record exists: is_demo={db_check['is_demo']}, status={db_check['status']}")
    except Exception as e:
        print(f"  [ERROR] Sync failed: {e}")
        return

    # -------------------------------------------------------------------------
    # STEP 3f: Supported Operation (Send / Remind)
    # -------------------------------------------------------------------------
    print("\nSTEP 3f: Attempting supported operation: Send Invoice (POST /v2/invoicing/invoices/{id}/send)...")
    send_success = False
    try:
        send_resp = send_sandbox_invoice(invoice_id, send_to_recipient=True)
        print("  [SUCCESS] PayPal invoice sent successfully:")
        print(f"    Response: {json.dumps(send_resp, indent=2)}")
        send_success = True
    except PayPalApiError as e:
        print(f"  [EXACT PAYPAL RESPONSE] PayPal send operation returned HTTP {e.status_code}:")
        print(f"    Name:    {e.error_name}")
        print(f"    Message: {e}")
        print(f"    Details: {json.dumps(e.details, indent=2) if e.details else 'None'}")
    except Exception as e:
        print(f"  [ERROR] Send operation encountered: {e}")

    # If send had country/permission constraints, let's test remind or document exact behavior
    if not send_success:
        print("\n  Testing Remind Operation (POST /v2/invoicing/invoices/{id}/remind)...")
        try:
            remind_resp = remind_sandbox_invoice(invoice_id, note="Courtesy reminder for pending invoice.")
            print("  [SUCCESS] PayPal reminder dispatched:")
            print(f"    Response: {json.dumps(remind_resp, indent=2)}")
        except PayPalApiError as e:
            print(f"  [EXACT PAYPAL RESPONSE] PayPal remind operation returned HTTP {e.status_code}:")
            print(f"    Name:    {e.error_name}")
            print(f"    Message: {e}")
            print(f"    Details: {json.dumps(e.details, indent=2) if e.details else 'None'}")
        except Exception as e:
            print(f"  [ERROR] Remind operation encountered: {e}")

    # -------------------------------------------------------------------------
    # STEP 3g: Re-fetch and Verify Payment State
    # -------------------------------------------------------------------------
    print("\nSTEP 3g: Re-fetching invoice and recording verified state...")
    try:
        verif = verify_sandbox_invoice_payment(invoice_id)
        print("  [SUCCESS] Payment state verified:")
        print(f"    Invoice ID:         {verif['invoice_id']}")
        print(f"    Is Paid Verified:   {verif['is_paid']}")
        print(f"    Current Status:     {verif['status']}")
        print(f"    Outstanding Amount: {verif['currency']} {verif['outstanding_amount']}")
        print(f"    Verified At:        {verif['verified_at']}")
    except Exception as e:
        print(f"  [ERROR] Payment verification failed: {e}")


if __name__ == "__main__":
    run_live_test()

