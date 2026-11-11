from datetime import date
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from backend.database import get_activity_logs, get_all_invoices, get_invoice_by_id
from backend.recovery.config import SCORING_VERSION
from backend.recovery.models import (
    ContributingFactor,
    InvoiceInput,
    InvoiceScoreResponse,
    StrategyEvaluation,
)
from backend.recovery.scoring import calculate_recovery_score
from backend.recovery.strategies import evaluate_strategies

router = APIRouter(prefix="/api/recovery", tags=["recovery"])


class InvoiceQueueItem(BaseModel):
    id: str
    invoice_number: str
    customer_name: str
    customer_email: str | None
    total_amount: Decimal
    outstanding_amount: Decimal
    currency: str
    status: str
    due_date: date
    days_overdue: int
    reminder_count: int
    last_reminder_date: date | None
    score: int | None
    priority: str | None
    is_actionable: bool
    recommended_action: str
    action_reason: str
    unavailable_information: list[str]
    notes: str | None
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
    items: list[InvoiceQueueItem]


class InvoiceDetailResponse(BaseModel):
    invoice: InvoiceQueueItem
    contributing_factors: list[ContributingFactor]
    explanation_summary: str
    scoring_version: str
    evaluated_at: date


def invoice_dict_to_input(data: dict[str, Any]) -> InvoiceInput:
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
    priority: str | None = Query(
        None, description="Filter by priority band (CRITICAL, HIGH, MEDIUM, LOW)"
    ),
    status: str | None = Query(
        None, description="Filter by invoice status (e.g. SENT, OVERDUE, PARTIALLY_PAID)"
    ),
    action: str | None = Query(
        None, description="Filter by recommended action"
    ),
    sort_by: str = Query(
        "score", description="Sort by: score, amount, days_overdue, due_date"
    ),
    sort_dir: str = Query(
        "desc", description="Sort direction: asc or desc"
    ),
    today: date | None = Query(
        None, description="Deterministic evaluation reference date"
    ),
):
    """
    Returns prioritized recovery queue computed deterministically.
    Excludes not-yet-due invoices (days_overdue <= 0) by default per spec.
    """
    eval_today = today or date.today()
    invoices = get_all_invoices()

    items: list[InvoiceQueueItem] = []
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
    today: date | None = Query(
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
    today: date | None = Query(
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


class DashboardStatsResponse(BaseModel):
    total_invoices_count: int
    paid_count: int
    unpaid_count: int
    overdue_count: int
    draft_count: int
    total_outstanding_usd: Decimal
    critical_priority_count: int
    high_priority_count: int
    medium_priority_count: int
    low_priority_count: int
    live_sandbox_count: int
    demo_count: int
    recent_activity: list[dict[str, Any]]


@router.get("/stats", response_model=DashboardStatsResponse)
def get_dashboard_stats(
    today: date | None = Query(None, description="Reference date for statistics"),
):
    """Command Center summary metrics computed live from backend records.
    Conforms to RULES.md (§3, §10).
    """
    from backend.database import get_activity_logs
    eval_today = today or date.today()
    invoices = get_all_invoices()

    total_invoices = len(invoices)
    paid_count = 0
    unpaid_count = 0
    overdue_count = 0
    draft_count = 0
    total_outstanding = Decimal("0.00")
    crit_count = 0
    high_count = 0
    med_count = 0
    low_count = 0
    live_sbx_count = 0
    demo_count = 0

    for inv in invoices:
        st = inv["status"].upper()
        is_demo = bool(inv.get("is_demo", True))
        if is_demo:
            demo_count += 1
        else:
            live_sbx_count += 1

        if st == "PAID":
            paid_count += 1
        elif st == "DRAFT":
            draft_count += 1
        else:
            unpaid_count += 1
            if inv.get("currency", "USD") == "USD":
                total_outstanding += inv["outstanding_amount"]
            
            # Check overdue
            due = inv.get("due_date")
            if due and (eval_today - due).days > 0:
                overdue_count += 1

            # Score priority
            inp = invoice_dict_to_input(inv)
            res = calculate_recovery_score(inp, today=eval_today)
            if res.priority == "CRITICAL":
                crit_count += 1
            elif res.priority == "HIGH":
                high_count += 1
            elif res.priority == "MEDIUM":
                med_count += 1
            elif res.priority == "LOW":
                low_count += 1

    recent_logs = get_activity_logs()[:10]

    return DashboardStatsResponse(
        total_invoices_count=total_invoices,
        paid_count=paid_count,
        unpaid_count=unpaid_count,
        overdue_count=overdue_count,
        draft_count=draft_count,
        total_outstanding_usd=total_outstanding,
        critical_priority_count=crit_count,
        high_priority_count=high_count,
        medium_priority_count=med_count,
        low_priority_count=low_count,
        live_sandbox_count=live_sbx_count,
        demo_count=demo_count,
        recent_activity=recent_logs,
    )


@router.get("/audit-logs", response_model=list[dict[str, Any]])
def get_audit_logs_endpoint(invoice_id: str | None = Query(None)):
    """Retrieve immutable recovery audit activity logs."""
    return get_activity_logs(invoice_id=invoice_id)
