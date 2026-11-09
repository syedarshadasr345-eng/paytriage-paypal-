"""
PayTriage Actions & Approval Gate — Schemas
Strictly conforms to phase5.md and RULES.md (§7, §8).
"""

from typing import Any, Literal

from pydantic import BaseModel, Field

ActionType = Literal[
    "record_copied_reminder",
    "paypal_send_invoice",
    "paypal_remind_invoice",
]

ApprovalStatus = Literal[
    "draft",
    "copied",
    "approved",
    "executed",
    "verified",
    "failed",
    "expired",
    "rejected",
]


class ActionProposeRequest(BaseModel):
    invoice_id: str = Field(..., description="Target invoice ID")
    action_type: ActionType = Field(..., description="Allowed action type: record_copied_reminder, paypal_send_invoice, paypal_remind_invoice")
    parameters: dict[str, Any] = Field(default_factory=dict, description="Action parameters (e.g. subject, body/note, tone)")


class ActionProposeResponse(BaseModel):
    approval_id: str
    invoice_id: str
    action_type: ActionType
    parameters: dict[str, Any]
    hash: str
    status: ApprovalStatus
    created_by: str
    created_at: str
    expires_at: str


class ActionExecuteRequest(BaseModel):
    action_type: ActionType = Field(..., description="Must match approved action_type")
    parameters: dict[str, Any] = Field(..., description="Must exactly match approved parameters to satisfy SHA-256 integrity check")


class ActionExecuteResponse(BaseModel):
    approval_id: str
    invoice_id: str
    action_type: ActionType
    status: ApprovalStatus
    verified: bool
    details: str
    executed_at: str

