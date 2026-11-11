"""
PayTriage Actions & Approval Gate — Router
Endpoints for human-in-the-loop action proposals, approvals, and execution.
Strictly conforms to phase5.md and RULES.md (§7, §8).
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query

from backend.actions.schemas import (
    ActionExecuteRequest,
    ActionExecuteResponse,
    ActionProposeRequest,
    ActionProposeResponse,
)
from backend.actions.service import (
    approve_action,
    execute_action,
    propose_action,
)
from backend.auth.service import get_current_user, require_merchant_user
from backend.database import get_approval_by_id, list_approvals
from backend.rate_limit import rate_limiter

router = APIRouter(prefix="/api/actions", tags=["actions"], dependencies=[Depends(rate_limiter("actions"))])


@router.post("/propose", response_model=ActionProposeResponse)
def propose_action_endpoint(
    req: ActionProposeRequest,
    user: dict[str, Any] = Depends(get_current_user),
):
    """Propose an action for approval. AI agents and merchants can propose; only merchants can approve."""
    return propose_action(req, user)


@router.post("/{approval_id}/approve", response_model=ActionProposeResponse)
def approve_action_endpoint(
    approval_id: str = Path(..., description="Approval ID to approve"),
    user: dict[str, Any] = Depends(require_merchant_user),
):
    """Approve a proposed action. Strictly restricted to human merchants (AI cannot approve)."""
    return approve_action(approval_id, user)


@router.post("/{approval_id}/execute", response_model=ActionExecuteResponse)
def execute_action_endpoint(
    approval_id: str = Path(..., description="Approval ID to execute"),
    req: ActionExecuteRequest = ...,
    user: dict[str, Any] = Depends(require_merchant_user),
):
    """Execute an approved action. Strictly verifies SHA-256 hash integrity, blocks duplicates, and verifies results."""
    return execute_action(approval_id, req, user)


@router.get("", response_model=list[ActionProposeResponse])
def list_approvals_endpoint(
    invoice_id: str | None = Query(None, description="Filter by invoice ID"),
    user: dict[str, Any] = Depends(get_current_user),
):
    """List action approvals for the current merchant."""
    import json
    records = list_approvals(invoice_id=invoice_id, merchant_id=user.get("merchant_id", "merchant_demo"))
    responses = []
    for r in records:
        responses.append(
            ActionProposeResponse(
                approval_id=r["id"],
                invoice_id=r["invoice_id"],
                action_type=r["action_type"],
                parameters=json.loads(r["parameters_json"]),
                hash=r["hash"],
                status=r["status"],
                created_by=r["created_by"],
                created_at=r["created_at"],
                expires_at=r["expires_at"],
            )
        )
    return responses


@router.get("/{approval_id}", response_model=ActionProposeResponse)
def get_approval_endpoint(
    approval_id: str = Path(..., description="Approval ID"),
    user: dict[str, Any] = Depends(get_current_user),
):
    """Retrieve details of a single action approval."""
    import json
    r = get_approval_by_id(approval_id)
    if not r:
        raise HTTPException(status_code=404, detail=f"Approval '{approval_id}' not found.")
    if r.get("merchant_id") != user.get("merchant_id", "merchant_demo"):
        raise HTTPException(status_code=403, detail="Forbidden: Ownership mismatch.")

    return ActionProposeResponse(
        approval_id=r["id"],
        invoice_id=r["invoice_id"],
        action_type=r["action_type"],
        parameters=json.loads(r["parameters_json"]),
        hash=r["hash"],
        status=r["status"],
        created_by=r["created_by"],
        created_at=r["created_at"],
        expires_at=r["expires_at"],
    )

