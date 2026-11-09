"""
Script to create 4 Sandbox invoices with different due dates via PayPal service.
Tests whether PayPal Invoicing V2 accepts a past due date for overdue testing.
If rejected, captures the exact error and uses the nearest allowed date.
Syncs all 4 invoices into SQLite database as is_demo=False.
"""

import json
import sys
import time
from datetime import date, timedelta
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

from backend.paypal.client import PayPalApiError
from backend.paypal.config import is_paypal_configured
from backend.paypal.invoices import create_sandbox_invoice, sync_paypal_invoice

if not is_paypal_configured():
    print("PayPal is not configured.")
    sys.exit(1)

print("=" * 60)
print("Creating 4 PayPal Sandbox Invoices")
print("=" * 60)

today = date.today()

# Invoice configurations to create
# Invoice 1: Overdue target (try 15 days in the past)
# Invoice 2: Overdue target (try 7 days in the past)
# Invoice 3: Due today / 1 day
# Invoice 4: Future due (14 days)

targets = [
    {
        "name": "Target 1 (Past Due -15 days)",
        "due_date": today - timedelta(days=15),
        "amount": "1200.00",
        "customer": "Apex Global Solutions",
        "email": "billing@apexsolutions.example.com",
    },
    {
        "name": "Target 2 (Past Due -7 days)",
        "due_date": today - timedelta(days=7),
        "amount": "650.00",
        "customer": "Crestview Media Group",
        "email": "finance@crestviewmedia.example.com",
    },
    {
        "name": "Target 3 (Due in 3 days)",
        "due_date": today + timedelta(days=3),
        "amount": "3100.00",
        "customer": "BluePeak Logistics LLC",
        "email": "ap@bluepeaklogistics.example.com",
    },
    {
        "name": "Target 4 (Due in 14 days)",
        "due_date": today + timedelta(days=14),
        "amount": "4800.00",
        "customer": "Starlight Dynamics",
        "email": "payments@starlightdynamics.example.com",
    },
]

created_invoices = []

for idx, t in enumerate(targets, start=1):
    print(f"\n[{idx}/4] Creating {t['name']} with due_date={t['due_date']}...")
    payload = {
        "invoice_number": f"INV-SBX-{int(time.time())}-{idx}",
        "customer_name": t["customer"],
        "customer_email": t["email"],
        "total_amount": t["amount"],
        "currency": "USD",
        "due_date": t["due_date"].isoformat(),
        "notes": f"Phase 5 Live Sandbox Invoice {idx} ({t['name']})",
        "item_name": "Consulting Services",
    }

    try:
        inv = create_sandbox_invoice(payload)
        print(f"  [SUCCESS] Created invoice ID: {inv.id} (status={inv.status})")
        sync_res = sync_paypal_invoice(inv.id)
        print(f"  [SYNCED] App Status: {sync_res.app_status}, Amount: {sync_res.currency} {sync_res.outstanding_amount}")
        created_invoices.append({"id": inv.id, "due_date": t["due_date"].isoformat(), "status": inv.status})
    except PayPalApiError as e:
        print(f"  [PAYPAL API ERROR] HTTP {e.status_code}: {e.error_name}")
        print(f"  Message: {e}")
        print(f"  Details: {json.dumps(e.details, indent=2) if e.details else 'None'}")
        
        # If rejected due to past due date, try nearest allowed date (today)
        print("  Retrying with nearest allowed date (today)...")
        payload["due_date"] = today.isoformat()
        try:
            inv = create_sandbox_invoice(payload)
            print(f"  [FALLBACK SUCCESS] Created invoice ID: {inv.id} with due_date={today.isoformat()}")
            sync_res = sync_paypal_invoice(inv.id)
            created_invoices.append({"id": inv.id, "due_date": today.isoformat(), "status": inv.status})
        except Exception as retry_err:
            print(f"  [FALLBACK FAILED]: {retry_err}")
    except Exception as e:
        print(f"  [FAILED]: {e}")

print("\n" + "=" * 60)
print(f"Completed! {len(created_invoices)} invoices successfully created and synced into DB.")
print("=" * 60)

