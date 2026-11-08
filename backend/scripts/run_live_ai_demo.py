"""
PayTriage AI — Live AI Smoke Test for 3 Demo Invoices
Invokes explain and reminder for 3 demo invoices with real GEMINI_API_KEY.
Outputs raw JSON with secrets hidden, reports source and fallback_reason.
"""

import os
import sys
import json
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

from backend.ai.config import get_gemini_api_key, GEMINI_MODEL
from backend.ai.client import GeminiClient
from backend.ai.explainer import explain_invoice_recovery
from backend.ai.reminders import generate_or_regenerate_reminder
from backend.seed import seed_database
from datetime import date

DEMO_INVOICES = ["INV-MOD-007", "INV-HIGH-008", "INV-SEV-009"]
TODAY = date(2026, 11, 1)

def run():
    api_key = get_gemini_api_key()
    print("=" * 60)
    print("LIVE AI TEST FOR 3 DEMO INVOICES")
    print(f"Model: {GEMINI_MODEL}")
    print(f"API Key Configured: {bool(api_key)}")
    print("=" * 60)
    
    seed_database(base_date=TODAY)
    real_client = GeminiClient(api_key=api_key) if api_key else None

    for inv_id in DEMO_INVOICES:
        print(f"\n--- INVOICE {inv_id} ---")
        # 1. Explain
        print(f"\n[EXPLAIN] Calling explain_invoice_recovery({inv_id})...")
        exp_res = explain_invoice_recovery(inv_id, today=TODAY, client=real_client)
        exp_dict = exp_res.model_dump()
        print("Raw JSON Response:")
        print(json.dumps(exp_dict, indent=2, default=str))
        print(f"Result -> source: {exp_res.source}, fallback_reason: {exp_res.fallback_reason}")

        # 2. Reminder
        print(f"\n[REMINDER] Calling generate_or_regenerate_reminder({inv_id})...")
        rem_res = generate_or_regenerate_reminder(inv_id, client=real_client)
        rem_dict = rem_res.model_dump()
        print("Raw JSON Response:")
        print(json.dumps(rem_dict, indent=2, default=str))
        print(f"Result -> source: {rem_res.source}, fallback_reason: {rem_res.fallback_reason}")

if __name__ == "__main__":
    run()
