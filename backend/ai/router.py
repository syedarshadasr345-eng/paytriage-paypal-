"""
PayTriage AI — FastAPI Router for AI Service Endpoints
Strictly conforms to phase3.md and RULES.md (§4, §6).
Endpoints:
- POST /api/ai/invoices/{id}/explain
- POST /api/ai/invoices/{id}/reminder
- GET  /api/ai/invoices/{id}/reminders
- GET  /api/ai/reminders/{draft_id}
- PUT  /api/ai/reminders/{draft_id}
- POST /api/ai/reminders/{draft_id}/copy
- POST /api/ai/assistant
"""

from datetime import date
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Query, Path

from backend.ai.schemas import (
    ExplanationResponse,
    ExplanationRequest,
    ReminderCreateRequest,
    ReminderEditRequest,
    ReminderDraftResponse,
    ReminderCopyResponse,
    AssistantMessageRequest,
    AssistantResponse,
)
from backend.ai.explainer import explain_invoice_recovery
from backend.ai.reminders import (
    generate_or_regenerate_reminder,
    edit_reminder_draft,
    copy_reminder_draft,
)
from backend.ai.assistant import ask_assistant
from backend.database import get_reminder_draft, list_reminder_drafts, get_invoice_by_id

router = APIRouter(prefix="/api/ai", tags=["ai"])


@router.post("/invoices/{id}/explain", response_model=ExplanationResponse)
def explain_invoice_endpoint(
    id: str = Path(..., description="Invoice ID to explain"),
    req: Optional[ExplanationRequest] = None,
    today: Optional[date] = Query(None, description="Optional ISO evaluation reference date"),
):
    """Generate grounded recovery explanation for an invoice with deterministic fallback."""
    question = req.question if req else None
    try:
        return explain_invoice_recovery(invoice_id=id, today=today, question=question)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Explanation generation failed: {str(e)}")


@router.post("/invoices/{id}/reminder", response_model=ReminderDraftResponse)
def generate_reminder_endpoint(
    id: str = Path(..., description="Invoice ID to draft reminder for"),
    req: Optional[ReminderCreateRequest] = None,
):
    """Generate or regenerate a payment reminder draft (draft status only, never sent)."""
    tone = req.tone if req else None
    try:
        return generate_or_regenerate_reminder(invoice_id=id, tone=tone)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Reminder generation failed: {str(e)}")


@router.get("/invoices/{id}/reminders", response_model=List[ReminderDraftResponse])
def list_invoice_reminders_endpoint(
    id: str = Path(..., description="Invoice ID"),
):
    """List all reminder drafts for a given invoice."""
    inv = get_invoice_by_id(id)
    if not inv:
        raise HTTPException(status_code=404, detail=f"Invoice '{id}' not found.")
    records = list_reminder_drafts(invoice_id=id)
    return [ReminderDraftResponse(**r) for r in records]


@router.get("/reminders/{draft_id}", response_model=ReminderDraftResponse)
def get_reminder_endpoint(
    draft_id: str = Path(..., description="Reminder draft ID"),
):
    """Retrieve details of a single reminder draft."""
    record = get_reminder_draft(draft_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Reminder draft '{draft_id}' not found.")
    return ReminderDraftResponse(**record)


@router.put("/reminders/{draft_id}", response_model=ReminderDraftResponse)
def edit_reminder_endpoint(
    draft_id: str = Path(..., description="Reminder draft ID"),
    req: ReminderEditRequest = ...,
):
    """Edit subject or body of an existing reminder draft."""
    try:
        return edit_reminder_draft(draft_id, req)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/reminders/{draft_id}/copy", response_model=ReminderCopyResponse)
def copy_reminder_endpoint(
    draft_id: str = Path(..., description="Reminder draft ID"),
):
    """Record that merchant copied draft text to clipboard. Updates status to 'copied'."""
    try:
        return copy_reminder_draft(draft_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/assistant", response_model=AssistantResponse)
def assistant_endpoint(
    req: AssistantMessageRequest,
    today: Optional[date] = Query(None, description="Optional ISO evaluation reference date"),
):
    """Interactive assistant supporting read-only triage tools and draft generation."""
    return ask_assistant(
        query=req.message,
        conversation_id=req.conversation_id,
        today=today,
    )
