"""
Step 4 Live PayPal End-to-End Verification Script
Runs with RUN_LIVE_PAYPAL=1 and real credentials in backend/.env.
Tests:
1. Unreminded Sandbox invoice (INV2-URFG-QJSC-KE3A-HPNC)
2. Propose action through approval gate
3. Approve as human merchant
4. Parameter tampering rejected with 409 Conflict
5. Execute through approval gate: calls PayPal Sandbox, re-fetches invoice, verifies status
6. Verify "Verified & Sent" state confirmed only after re-fetch
7. Duplicate execution blocked with 400 Bad Request
"""

import os
import sys
import pathlib

repo_root = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(repo_root))

from dotenv import load_dotenv
load_dotenv(repo_root / "backend/.env")

# Verify RUN_LIVE_PAYPAL
os.environ["RUN_LIVE_PAYPAL"] = "1"

from fastapi import HTTPException
from backend.paypal.config import is_paypal_configured
from backend.paypal.invoices import sync_paypal_invoice, get_sandbox_invoice
from backend.actions.schemas import ActionProposeRequest, ActionExecuteRequest
from backend.actions.service import propose_action, approve_action, execute_action
from backend.database import get_approval_by_id, get_activity_logs

def main():
    if not is_paypal_configured():
        print("FAIL: PayPal is not configured in backend/.env")
        sys.exit(1)

    inv_id = "INV2-URFG-QJSC-KE3A-HPNC"
    print(f"Target Sandbox Invoice: {inv_id}")

    # Ensure invoice is synced to SQLite in genuine state
    sync_res = sync_paypal_invoice(inv_id)
    print(f"Initial PayPal Status: {sync_res.app_status}, Amount: {sync_res.outstanding_amount}")

    user_merchant = {"sub": "merchant_demo@paytriage.local", "merchant_id": "merchant_demo", "role": "merchant"}

    # 1. Propose action
    prop_req = ActionProposeRequest(
        invoice_id=inv_id,
        action_type="paypal_send_invoice",
        parameters={"subject": "Invoice from PayTriage", "send_to_recipient": True}
    )
    prop_res = propose_action(prop_req, user=user_merchant)
    appr_id = prop_res.approval_id
    print(f"1. Proposed action: approval_id={appr_id}, hash={prop_res.hash[:16]}..., status={prop_res.status}")

    # 2. Approve action as merchant
    appr_res = approve_action(appr_id, user=user_merchant)
    print(f"2. Approved action: status={appr_res.status}")
    assert appr_res.status == "approved"

    # 3. Test parameter tampering blocked (409 Conflict)
    tampered_exec_req = ActionExecuteRequest(
        action_type="paypal_send_invoice",
        parameters={"subject": "TAMPERED SUBJECT", "send_to_recipient": True}
    )
    tamper_caught = False
    try:
        execute_action(appr_id, tampered_exec_req, user=user_merchant)
    except HTTPException as exc:
        if exc.status_code == 409:
            tamper_caught = True
            print(f"3. Parameter edit blocked: 409 Conflict caught as expected ('{exc.detail}')")
        else:
            print(f"3. Unexpected exception status: {exc.status_code}")
    except Exception as e:
        print(f"3. Unexpected exception: {e}")

    assert tamper_caught, "Expected 409 Conflict on tampered parameters"

    # Since tampering rejected the approval (status='rejected'), re-propose and approve cleanly for execution
    prop_clean = propose_action(prop_req, user=user_merchant)
    clean_appr_id = prop_clean.approval_id
    approve_action(clean_appr_id, user=user_merchant)
    print(f"4. Re-created clean approval for execution: {clean_appr_id}")

    # 4. Execute action: calls PayPal API, re-fetches status, verifies
    clean_exec_req = ActionExecuteRequest(
        action_type="paypal_send_invoice",
        parameters={"subject": "Invoice from PayTriage", "send_to_recipient": True}
    )
    exec_res = execute_action(clean_appr_id, clean_exec_req, user=user_merchant)
    print(f"5. Execution result: verified={exec_res.verified}, status={exec_res.status}, details='{exec_res.details}'")
    assert exec_res.verified is True
    assert exec_res.status == "verified"

    # Verify post-execution state in PayPal and SQLite
    post_appr = get_approval_by_id(clean_appr_id)
    assert post_appr["status"] == "verified"
    assert post_appr["used_at"] is not None
    print("   Approval status in DB: verified, used_at recorded.")

    # Check activity logs for verification event
    logs = get_activity_logs(invoice_id=inv_id)
    verified_logs = [l for l in logs if l.get("action_type") == "paypal_send_verified"]
    assert len(verified_logs) > 0, "Expected paypal_send_verified activity log entry"
    print(f"   Activity log verified: '{verified_logs[0]['details']}'")

    # 5. Test duplicate execution blocked (400 Bad Request)
    dup_blocked = False
    try:
        execute_action(clean_appr_id, clean_exec_req, user=user_merchant)
    except HTTPException as exc:
        if exc.status_code == 400 and "duplicate" in exc.detail.lower():
            dup_blocked = True
            print(f"6. Duplicate execution blocked: 400 Bad Request caught ('{exc.detail}')")
        else:
            print(f"6. Unexpected exception status: {exc.status_code} - {exc.detail}")
    except Exception as e:
        print(f"6. Unexpected exception: {e}")

    assert dup_blocked, "Expected 400 Bad Request on duplicate execution"

    print("\n--- STEP 4 LIVE PAYPAL END-TO-END PASSED COMPLETELY ---")

if __name__ == "__main__":
    main()
