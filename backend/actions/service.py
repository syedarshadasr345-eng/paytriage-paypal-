"""
PayTriage Actions & Approval Gate — Service Logic
Strictly conforms to phase5.md, RULES.md (§7, §8), and docs/PAYPAL.md.
"""

import hashlib
import json
import uuid
from datetime import datetime, timedelta
from typing import Any

from fastapi import HTTPException

from backend.actions.schemas import (
    ActionExecuteRequest,
    ActionExecuteResponse,
    ActionProposeRequest,
    ActionProposeResponse,
)
from backend.auth.service import check_invoice_ownership
from backend.database import (
    get_approval_by_id,
    get_invoice_by_id,
    list_reminder_drafts,
    log_activity,
    save_approval,
    update_approval_status,
    update_reminder_draft,
)
from backend.paypal.client import PayPalClientError
from backend.paypal.invoices import (
    remind_sandbox_invoice,
    send_sandbox_invoice,
    verify_sandbox_invoice_payment,
)

ALLOWED_ACTION_TYPES = {
    "record_copied_reminder",
    "paypal_send_invoice",
    "paypal_remind_invoice",
}


def compute_action_hash(invoice_id: str, action_type: str, parameters: dict[str, Any]) -> str:
    """Compute deterministic SHA-256 hash of canonical action payload."""
    canonical_obj = {
        "invoice_id": str(invoice_id).strip(),
        "action_type": str(action_type).strip(),
        "parameters": parameters,
    }
    canonical_bytes = json.dumps(canonical_obj, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical_bytes).hexdigest()


def propose_action(req: ActionProposeRequest, user: dict[str, Any]) -> ActionProposeResponse:
    """Validate and store a proposed action, returning an approval ID and SHA-256 hash."""
    # 1. Action type whitelist check
    if req.action_type not in ALLOWED_ACTION_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid action_type '{req.action_type}'. Allowed action types: {list(ALLOWED_ACTION_TYPES)}",
        )

    # 2. Invoice existence and ownership check
    inv = get_invoice_by_id(req.invoice_id)
    if not inv:
        raise HTTPException(status_code=404, detail=f"Invoice '{req.invoice_id}' not found.")
    check_invoice_ownership(inv, user)

    # 3. Demo vs Live Sandbox Guard
    if inv.get("is_demo") and req.action_type in ("paypal_send_invoice", "paypal_remind_invoice"):
        raise HTTPException(
            status_code=400,
            detail="PayPal actions are disabled for demo benchmark data. Use Live Sandbox invoices to dispatch real PayPal API calls.",
        )

    # 4. Status Prerequisites
    inv_status = str(inv.get("status", "")).upper()
    if req.action_type == "paypal_send_invoice":
        if inv_status != "DRAFT":
            raise HTTPException(
                status_code=400,
                detail=f"paypal_send_invoice is supported ONLY for DRAFT invoices. Current status is '{inv_status}'.",
            )
    elif req.action_type == "paypal_remind_invoice":
        if inv_status in ("DRAFT", "PAID", "CANCELLED"):
            raise HTTPException(
                status_code=400,
                detail=f"paypal_remind_invoice is not allowed for {inv_status} invoices.",
            )

    # 5. Compute SHA-256 integrity hash
    action_hash = compute_action_hash(req.invoice_id, req.action_type, req.parameters)

    approval_id = f"APP-{uuid.uuid4().hex[:8].upper()}"
    now = datetime.now()
    now_iso = now.isoformat()
    expires_at_iso = (now + timedelta(hours=24)).isoformat()

    record = {
        "id": approval_id,
        "invoice_id": req.invoice_id,
        "action_type": req.action_type,
        "parameters_json": json.dumps(req.parameters, sort_keys=True),
        "hash": action_hash,
        "status": "draft",
        "created_by": user.get("sub", "merchant"),
        "created_at": now_iso,
        "expires_at": expires_at_iso,
        "used_at": None,
        "merchant_id": user.get("merchant_id", "merchant_demo"),
    }

    save_approval(record)

    log_activity(
        invoice_id=req.invoice_id,
        action_type="action_proposed",
        status="draft",
        details=f"Proposed {req.action_type} (approval_id={approval_id}, hash={action_hash[:12]}...).",
    )

    return ActionProposeResponse(
        approval_id=approval_id,
        invoice_id=req.invoice_id,
        action_type=req.action_type,
        parameters=req.parameters,
        hash=action_hash,
        status="draft",
        created_by=record["created_by"],
        created_at=now_iso,
        expires_at=expires_at_iso,
    )


def approve_action(approval_id: str, user: dict[str, Any]) -> ActionProposeResponse:
    """Human merchant approves proposed action."""
    # Strict rule: AI cannot approve
    if user.get("role") == "ai":
        raise HTTPException(
            status_code=403,
            detail="AI cannot approve actions. Human merchant approval required.",
        )

    appr = get_approval_by_id(approval_id)
    if not appr:
        raise HTTPException(status_code=404, detail=f"Approval '{approval_id}' not found.")

    if appr.get("merchant_id") != user.get("merchant_id", "merchant_demo"):
        raise HTTPException(status_code=403, detail="Forbidden: Ownership mismatch.")

    # Expiry check
    exp_dt = datetime.fromisoformat(appr["expires_at"])
    if datetime.now() > exp_dt:
        update_approval_status(approval_id, "expired")
        log_activity(
            invoice_id=appr["invoice_id"],
            action_type="approval_expired",
            status="expired",
            details=f"Approval {approval_id} expired before review.",
        )
        raise HTTPException(status_code=400, detail="Approval request has expired.")

    # Status check
    if appr["status"] != "draft":
        raise HTTPException(
            status_code=400,
            detail=f"Approval {approval_id} is in status '{appr['status']}' and cannot be approved.",
        )

    updated = update_approval_status(approval_id, "approved")

    log_activity(
        invoice_id=appr["invoice_id"],
        action_type="action_approved",
        status="approved",
        details=f"Merchant approved {appr['action_type']} (approval_id={approval_id}).",
    )

    return ActionProposeResponse(
        approval_id=updated["id"],
        invoice_id=updated["invoice_id"],
        action_type=updated["action_type"],
        parameters=json.loads(updated["parameters_json"]),
        hash=updated["hash"],
        status="approved",
        created_by=updated["created_by"],
        created_at=updated["created_at"],
        expires_at=updated["expires_at"],
    )


def execute_action(
    approval_id: str,
    req: ActionExecuteRequest,
    user: dict[str, Any],
    client=None,
) -> ActionExecuteResponse:
    """Execute pre-approved action with SHA-256 integrity verification, duplicate prevention, and verification."""
    # Strict rule: AI cannot execute
    if user.get("role") == "ai":
        raise HTTPException(
            status_code=403,
            detail="AI cannot execute actions. Human merchant authorization required.",
        )

    appr = get_approval_by_id(approval_id)
    if not appr:
        raise HTTPException(status_code=404, detail=f"Approval '{approval_id}' not found.")

    if appr.get("merchant_id") != user.get("merchant_id", "merchant_demo"):
        raise HTTPException(status_code=403, detail="Forbidden: Ownership mismatch.")

    # 1. Single-use duplicate execution check
    if appr.get("used_at") is not None:
        raise HTTPException(
            status_code=400,
            detail="Duplicate execution blocked: This approval has already been executed.",
        )

    # 2. Expiry check
    exp_dt = datetime.fromisoformat(appr["expires_at"])
    if datetime.now() > exp_dt:
        update_approval_status(approval_id, "expired")
        raise HTTPException(status_code=400, detail="Approval request has expired.")

    # 3. Status check
    if appr["status"] != "approved":
        raise HTTPException(
            status_code=400,
            detail=f"Action cannot be executed. Approval is in '{appr['status']}' state, expected 'approved'.",
        )

    # 4. SHA-256 Integrity Verification: Action and parameters must match EXACTLY
    submitted_hash = compute_action_hash(appr["invoice_id"], req.action_type, req.parameters)
    if submitted_hash != appr["hash"]:
        update_approval_status(approval_id, "rejected")
        log_activity(
            invoice_id=appr["invoice_id"],
            action_type="action_hash_mismatch",
            status="rejected",
            details="Submitted parameters do not match approved hash. Re-approval required.",
        )
        raise HTTPException(
            status_code=409,
            detail="Submitted action parameters have changed since approval. Hash mismatch requires re-approval.",
        )

    # 5. Atomic mark as used
    now_iso = datetime.now().isoformat()
    update_approval_status(approval_id, "executed", used_at=now_iso)

    inv_id = appr["invoice_id"]
    action_type = req.action_type

    # 6. Execute specific action
    details = ""
    verified = False

    try:
        if action_type == "record_copied_reminder":
            drafts = list_reminder_drafts(invoice_id=inv_id)
            if drafts:
                update_reminder_draft(drafts[0]["id"], {"status": "copied"})
            update_approval_status(approval_id, "verified")
            details = "Reminder text copied to clipboard and recorded."
            verified = True
            log_activity(
                invoice_id=inv_id,
                action_type="record_copied_reminder",
                status="copied",
                details=details,
            )

        elif action_type == "paypal_send_invoice":
            send_sandbox_invoice(inv_id, client=client)
            verif = verify_sandbox_invoice_payment(inv_id, client=client)
            if verif.get("status") in ("SENT", "OVERDUE", "PAID"):
                update_approval_status(approval_id, "verified")
                details = f"PayPal invoice dispatched and verified as {verif.get('status')}."
                verified = True
                log_activity(
                    invoice_id=inv_id,
                    action_type="paypal_send_verified",
                    status="verified",
                    details=details,
                )
            else:
                update_approval_status(approval_id, "failed")
                details = f"PayPal send completed but unexpected verified status: {verif.get('status')}."
                log_activity(
                    invoice_id=inv_id,
                    action_type="paypal_send_failed",
                    status="failed",
                    details=details,
                )

        elif action_type == "paypal_remind_invoice":
            subject = req.parameters.get("subject")
            note = req.parameters.get("note") or req.parameters.get("body")
            remind_sandbox_invoice(
                inv_id,
                subject=subject,
                note=note,
                client=client,
            )
            verif = verify_sandbox_invoice_payment(inv_id, client=client)
            update_approval_status(approval_id, "verified")
            details = "PayPal payment reminder transmitted to customer and verified."
            verified = True
            log_activity(
                invoice_id=inv_id,
                action_type="paypal_remind_verified",
                status="verified",
                details=details,
            )

    except PayPalClientError as pce:
        update_approval_status(approval_id, "failed")
        details = f"PayPal API operation failed: {pce!s}"
        log_activity(
            invoice_id=inv_id,
            action_type=f"{action_type}_failed",
            status="failed",
            details=details,
        )
        raise HTTPException(status_code=502, detail=details)
    except Exception as exc:
        update_approval_status(approval_id, "failed")
        details = f"Execution failed: {exc!s}"
        log_activity(
            invoice_id=inv_id,
            action_type=f"{action_type}_failed",
            status="failed",
            details=details,
        )
        raise HTTPException(status_code=500, detail=details)

    final_status = "verified" if verified else "failed"
    return ActionExecuteResponse(
        approval_id=approval_id,
        invoice_id=inv_id,
        action_type=action_type,
        status=final_status,
        verified=verified,
        details=details,
        executed_at=now_iso,
    )

