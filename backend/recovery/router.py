from datetime import date
from decimal import Decimal
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from backend.database import get_all_invoices, get_invoice_by_id
from backend.recovery.models import (
    InvoiceInput,
    InvoiceScoreResponse,
    StrategyEvaluation,
    ContributingFactor,
)
from backend.recovery.scoring import calculate_recovery_score
from backend.recovery.strategies import evaluate_strategies
from backend.recovery.config import SCORING_VERSION

router = APIRouter(prefix="/api/recovery", tags=["recovery"])


class InvoiceQueueItem(BaseModel):
    id: str
    invoice_number: str
    customer_name: str
    customer_email: Optional[str]
    total_amount: Decimal
    outstanding_amount: Decimal
    currency: str
    status: str
    due_date: date
    days_overdue: int
    reminder_count: int
    last_reminder_date: Optional[date]
    score: Optional[int]
    priority: Optional[str]
    is_actionable: bool
    recommended_action: str
    action_reason: str
    unavailable_information: List[str]
    notes: Optional[str]
    is_demo: bool


class QueueResponse(BaseModel):
    evaluated_at: date
    scoring_version: str
    total_count: int
    actionable_count: int
    critical_count: int
    high_count: int
    medium_count: int
    low_count: int
    total_outstanding_usd: Decimal
    items: List[InvoiceQueueItem]


class InvoiceDetailResponse(BaseModel):
    invoice: InvoiceQueueItem
    contributing_factors: List[ContributingFactor]
    explanation_summary: str
    scoring_version: str
    evaluated_at: date


def invoice_dict_to_input(data: Dict[str, Any]) -> InvoiceInput:
    """Helper to convert database dictionary to validated InvoiceInput model."""
    return InvoiceInput(
        invoice_id=data["id"],
        customer_name=data.get("customer_name", "Customer"),
        customer_email=data.get("customer_email"),
        total_amount=data["total_amount"],
        outstanding_amount=data["outstanding_amount"],
        currency=data.get("currency", "USD"),
        status=data["status"],
        due_date=data["due_date"],
        reminder_count=data.get("reminder_count", 0),
        last_reminder_date=data.get("last_reminder_date"),
        payment_history=data.get("payment_history"),
        has_promise_to_pay=data.get("has_promise_to_pay", False),
        promise_due_date=data.get("promise_due_date"),
    )


@router.get("/queue", response_model=QueueResponse)
def get_recovery_queue(
    include_not_due: bool = Query(
        False, description="Whether to include not-yet-due invoices in queue"
    ),
    priority: Optional[str] = Query(
        None, description="Filter by priority band (CRITICAL, HIGH, MEDIUM, LOW)"
    ),
    status: Optional[str] = Query(
        None, description="Filter by invoice status (e.g. SENT, OVERDUE, PARTIALLY_PAID)"
    ),
    action: Optional[str] = Query(
        None, description="Filter by recommended action"
    ),
    sort_by: str = Query(
        "score", description="Sort by: score, amount, days_overdue, due_date"
    ),
    sort_dir: str = Query(
        "desc", description="Sort direction: asc or desc"
    ),
    today: Optional[date] = Query(
        None, description="Deterministic evaluation reference date"
    ),
):
    """
    Returns prioritized recovery queue computed deterministically.
    Excludes not-yet-due invoices (days_overdue <= 0) by default per spec.
    """
    eval_today = today or date.today()
    invoices = get_all_invoices()

    items: List[InvoiceQueueItem] = []
    actionable_count = 0
    critical_count = 0
    high_count = 0
    medium_count = 0
    low_count = 0
    total_outstanding_usd = Decimal("0.00")

    for raw in invoices:
        inv_input = invoice_dict_to_input(raw)
        scored: InvoiceScoreResponse = calculate_recovery_score(inv_input, today=eval_today)

        # Exclude not yet due unless explicitly requested
        if scored.days_overdue <= 0 and not include_not_due:
            continue

        # Filter by priority
        if priority and (scored.priority or "").upper() != priority.upper():
            continue

        # Filter by status
        if status and raw["status"].upper() != status.upper():
            continue

        # Filter by recommended action
        if action and scored.recommended_action.lower() != action.lower():
            continue

        if scored.is_actionable:
            actionable_count += 1

        if scored.priority == "CRITICAL":
            critical_count += 1
        elif scored.priority == "HIGH":
            high_count += 1
        elif scored.priority == "MEDIUM":
            medium_count += 1
        elif scored.priority == "LOW":
            low_count += 1

        if raw.get("currency", "USD").upper() == "USD":
            total_outstanding_usd += raw["outstanding_amount"]

        queue_item = InvoiceQueueItem(
            id=raw["id"],
            invoice_number=raw.get("invoice_number", raw["id"]),
            customer_name=raw["customer_name"],
            customer_email=raw.get("customer_email"),
            total_amount=raw["total_amount"],
            outstanding_amount=raw["outstanding_amount"],
            currency=raw.get("currency", "USD"),
            status=raw["status"],
            due_date=raw["due_date"],
            days_overdue=scored.days_overdue,
            reminder_count=raw.get("reminder_count", 0),
            last_reminder_date=raw.get("last_reminder_date"),
            score=scored.score,
            priority=scored.priority,
            is_actionable=scored.is_actionable,
            recommended_action=scored.recommended_action,
            action_reason=scored.action_reason,
            unavailable_information=scored.unavailable_information,
            notes=raw.get("notes"),
            is_demo=raw.get("is_demo", True),
        )
        items.append(queue_item)

    # Sorting
    reverse = sort_dir.lower() == "desc"
    if sort_by == "score":
        # Put None scores at the very end regardless of direction
        items.sort(
            key=lambda x: (-1 if x.score is None else x.score),
            reverse=reverse,
        )
    elif sort_by == "amount":
        items.sort(key=lambda x: x.outstanding_amount, reverse=reverse)
    elif sort_by == "days_overdue":
        items.sort(key=lambda x: x.days_overdue, reverse=reverse)
    elif sort_by == "due_date":
        items.sort(key=lambda x: x.due_date, reverse=reverse)

    return QueueResponse(
        evaluated_at=eval_today,
        scoring_version=SCORING_VERSION,
        total_count=len(items),
        actionable_count=actionable_count,
        critical_count=critical_count,
        high_count=high_count,
        medium_count=medium_count,
        low_count=low_count,
        total_outstanding_usd=total_outstanding_usd,
        items=items,
    )


@router.get("/invoices/{invoice_id}", response_model=InvoiceDetailResponse)
def get_invoice_detail(
    invoice_id: str,
    today: Optional[date] = Query(
        None, description="Deterministic evaluation reference date"
    ),
):
    """
    Returns detailed recovery score and contributing factor breakdown for an invoice.
    """
    eval_today = today or date.today()
    raw = get_invoice_by_id(invoice_id)
    if not raw:
        raise HTTPException(status_code=404, detail=f"Invoice '{invoice_id}' not found.")

    inv_input = invoice_dict_to_input(raw)
    scored: InvoiceScoreResponse = calculate_recovery_score(inv_input, today=eval_today)

    item = InvoiceQueueItem(
        id=raw["id"],
        invoice_number=raw.get("invoice_number", raw["id"]),
        customer_name=raw["customer_name"],
        customer_email=raw.get("customer_email"),
        total_amount=raw["total_amount"],
        outstanding_amount=raw["outstanding_amount"],
        currency=raw.get("currency", "USD"),
        status=raw["status"],
        due_date=raw["due_date"],
        days_overdue=scored.days_overdue,
        reminder_count=raw.get("reminder_count", 0),
        last_reminder_date=raw.get("last_reminder_date"),
        score=scored.score,
        priority=scored.priority,
        is_actionable=scored.is_actionable,
        recommended_action=scored.recommended_action,
        action_reason=scored.action_reason,
        unavailable_information=scored.unavailable_information,
        notes=raw.get("notes"),
        is_demo=raw.get("is_demo", True),
    )

    return InvoiceDetailResponse(
        invoice=item,
        contributing_factors=scored.contributing_factors,
        explanation_summary=scored.explanation_summary,
        scoring_version=scored.scoring_version,
        evaluated_at=scored.evaluated_at,
    )


@router.get("/invoices/{invoice_id}/strategies", response_model=StrategyEvaluation)
def get_invoice_strategies(
    invoice_id: str,
    today: Optional[date] = Query(
        None, description="Deterministic evaluation reference date"
    ),
):
    """
    Returns comparative evaluation of all 4 recovery strategies with advantages and limitations.
    """
    eval_today = today or date.today()
    raw = get_invoice_by_id(invoice_id)
    if not raw:
        raise HTTPException(status_code=404, detail=f"Invoice '{invoice_id}' not found.")

    inv_input = invoice_dict_to_input(raw)
    evaluation = evaluate_strategies(inv_input, today=eval_today)
    return evaluation
