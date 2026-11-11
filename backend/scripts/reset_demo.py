"""
PayTriage Demo Reset Script
Resets the database to a clean, fresh demonstration state.
Clears approvals, reminder drafts, activity logs, and re-seeds demo invoices.
Guarantees >= 2 unreminded live PayPal Sandbox invoices ready for live testing.
"""

import os
import sys
import pathlib

repo_root = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(repo_root))

from dotenv import load_dotenv
load_dotenv(repo_root / "backend/.env")

from backend.database import init_db, clear_invoices, get_db_connection
from backend.seed import seed_database

def reset_demo():
    print("Resetting PayTriage demo database...")

    # Clear transient state tables
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM approvals")
    c.execute("DELETE FROM reminder_drafts")
    c.execute("DELETE FROM activity_logs")
    conn.commit()
    conn.close()

    # Re-seed database with benchmark data and live sandbox invoices
    total_seeded = seed_database()
    print(f"Seeded {total_seeded} benchmark and sandbox invoice records.")

    # Verify >= 2 unreminded Sandbox invoices exist
    conn = get_db_connection()
    c = conn.cursor()
    sandbox_invoices = c.execute(
        "SELECT id, customer_name, status, outstanding_amount, reminder_count FROM invoices WHERE is_demo = 0"
    ).fetchall()
    conn.close()

    unreminded = [inv for inv in sandbox_invoices if inv[4] == 0]
    print(f"\nLive PayPal Sandbox Invoices found: {len(sandbox_invoices)}")
    print(f"Unreminded Sandbox Invoices found:  {len(unreminded)}")
    for inv in unreminded:
        print(f"  - {inv[0]}: {inv[1]} | Status: {inv[2]} | Amount: USD {inv[3]} | Reminders: {inv[4]}")

    if len(unreminded) < 2:
        print(f"FAIL: Expected >= 2 unreminded Sandbox invoices, found {len(unreminded)}")
        sys.exit(1)

    print("\nDEMO RESET COMPLETE: Database is clean and ready.")

if __name__ == "__main__":
    reset_demo()
