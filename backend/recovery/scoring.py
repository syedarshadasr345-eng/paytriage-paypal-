from datetime import date

from backend.recovery.actions import RECOGNIZED_STATUSES, determine_next_best_action
from backend.recovery.config import (
    AMOUNT_WEIGHTS_USD,
    BROKEN_PROMISE_POINTS,
    COMPONENT_D_MAX_POINTS,
    CUSTOMER_HISTORY_MISSING_POINTS,
    DAYS_OVERDUE_WEIGHTS,
    PAYMENT_HISTORY_POINTS,
    PRIORITY_BANDS,
    REMINDER_COUNT_WEIGHTS,
    SCORING_VERSION,
)
from backend.recovery.models import (
    ContributingFactor,
    InvoiceInput,
    InvoiceScoreResponse,
)


def calculate_recovery_score(invoice: InvoiceInput, today: date) -> InvoiceScoreResponse:
    """
    Pure, deterministic recovery scoring function.
    Evaluates strictly against 'today' reference date and never reads system clock.
    """
    days_overdue = (today - invoice.due_date).days
    status = invoice.status.upper()

    # 1. Excluded Statuses (Paid, Cancelled, Disputed, Draft, or Unrecognized)
    if status in ("PAID", "CANCELLED", "DISPUTED", "DRAFT") or status not in RECOGNIZED_STATUSES:
        action, reason = determine_next_best_action(invoice, today)
        return InvoiceScoreResponse(
            invoice_id=invoice.invoice_id,
            status=status,
            is_actionable=False,
            days_overdue=days_overdue,
            score=None,
            priority=None,
            contributing_factors=[],
            recommended_action=action,
            action_reason=reason,
            unavailable_information=[],
            explanation_summary=f"Invoice status is {status}. Ordinary recovery scoring is not applicable.",
            scoring_version=SCORING_VERSION,
            evaluated_at=today,
        )

    # 2. Not Yet Due (days_overdue <= 0)
    if days_overdue <= 0:
        action, reason = determine_next_best_action(invoice, today)
        return InvoiceScoreResponse(
            invoice_id=invoice.invoice_id,
            status=status,
            is_actionable=False,
            days_overdue=days_overdue,
            score=None,
            priority=None,
            contributing_factors=[],
            recommended_action=action,
            action_reason=reason,
            unavailable_information=[],
            explanation_summary="Invoice is not yet due. No recovery score is assigned.",
            scoring_version=SCORING_VERSION,
            evaluated_at=today,
        )

    # 3. Actionable Invoices (OVERDUE, PARTIALLY_PAID)
    contributing_factors: list[ContributingFactor] = []
    unavailable_info: list[str] = []

    # Component A: Days Overdue (Up to 40 pts)
    comp_a_points = 0
    for tier in DAYS_OVERDUE_WEIGHTS:
        min_d = tier["min_days"]
        max_d = tier["max_days"]
        if max_d is None:
            if days_overdue >= min_d:
                comp_a_points = tier["points"]
                contributing_factors.append(ContributingFactor(
                    factor_name=tier["factor"],
                    points=tier["points"],
                    description=tier["description"],
                ))
                break
        else:
            if min_d <= days_overdue <= max_d:
                comp_a_points = tier["points"]
                contributing_factors.append(ContributingFactor(
                    factor_name=tier["factor"],
                    points=tier["points"],
                    description=tier["description"],
                ))
                break

    # Component B: Outstanding Amount (USD only, Up to 25 pts)
    comp_b_points = 0
    if invoice.currency == "USD":
        for tier in AMOUNT_WEIGHTS_USD:
            min_a = tier["min_amount"]
            max_a = tier["max_amount"]
            if max_a is None:
                if invoice.outstanding_amount >= min_a:
                    comp_b_points = tier["points"]
                    contributing_factors.append(ContributingFactor(
                        factor_name=tier["factor"],
                        points=tier["points"],
                        description=tier["description"],
                    ))
                    break
            else:
                if min_a <= invoice.outstanding_amount <= max_a:
                    comp_b_points = tier["points"]
                    contributing_factors.append(ContributingFactor(
                        factor_name=tier["factor"],
                        points=tier["points"],
                        description=tier["description"],
                    ))
                    break
    else:
        # Non-USD currency: 0 points, note unavailable
        contributing_factors.append(ContributingFactor(
            factor_name="amount_non_usd_excluded",
            points=0,
            description=f"Invoice currency is {invoice.currency}. Amount tier scoring applies strictly to USD.",
            is_assumption=False,
        ))
        unavailable_info.append("amount_scoring_unavailable_for_currency")

    # Component C: Reminder History (Up to 20 pts)
    if invoice.reminder_count in REMINDER_COUNT_WEIGHTS:
        rem_tier = REMINDER_COUNT_WEIGHTS[invoice.reminder_count]
    else:
        rem_tier = REMINDER_COUNT_WEIGHTS[3]
    comp_c_points = rem_tier["points"]
    contributing_factors.append(ContributingFactor(
        factor_name=rem_tier["factor"],
        points=rem_tier["points"],
        description=rem_tier["description"],
    ))

    # Component D: Customer History & Risk Signals (Up to 15 pts)
    comp_d_subtotal = 0
    if invoice.payment_history and invoice.payment_history in PAYMENT_HISTORY_POINTS:
        hist_tier = PAYMENT_HISTORY_POINTS[invoice.payment_history]
        comp_d_subtotal += hist_tier["points"]
        contributing_factors.append(ContributingFactor(
            factor_name=hist_tier["factor"],
            points=hist_tier["points"],
            description=hist_tier["description"],
            is_assumption=False,
        ))
    else:
        # Missing customer history: baseline neutral 5 pts as an assumption
        comp_d_subtotal += CUSTOMER_HISTORY_MISSING_POINTS
        contributing_factors.append(ContributingFactor(
            factor_name="customer_history_unavailable",
            points=CUSTOMER_HISTORY_MISSING_POINTS,
            description="Customer payment history unavailable. Baseline neutral factor (5 pts) applied as an assumption.",
            is_assumption=True,
        ))
        unavailable_info.append("customer_payment_history")

    # Check for Broken Promise to Pay (+10 pts)
    if invoice.has_promise_to_pay and invoice.promise_due_date and invoice.promise_due_date < today:
        comp_d_subtotal += BROKEN_PROMISE_POINTS
        contributing_factors.append(ContributingFactor(
            factor_name="broken_promise",
            points=BROKEN_PROMISE_POINTS,
            description=f"Debtor missed promised payment date of {invoice.promise_due_date}.",
            is_assumption=False,
        ))

    # Clamp Component D to maximum 15 points
    comp_d_points = min(COMPONENT_D_MAX_POINTS, comp_d_subtotal)

    # Compute Total Clamped Score (0 to 100)
    total_score = max(0, min(100, comp_a_points + comp_b_points + comp_c_points + comp_d_points))

    # Priority Band Assignment
    priority = "LOW"
    for band in PRIORITY_BANDS:
        if band["min_score"] <= total_score <= band["max_score"]:
            priority = band["priority"]
            break

    # Next-Best-Action
    action, reason = determine_next_best_action(invoice, today)

    # Plain-language explanation
    assumptions_note = " (includes baseline assumption for missing customer history)" if "customer_payment_history" in unavailable_info else ""
    summary = (
        f"Invoice {invoice.invoice_id} is evaluated at Priority {priority} (Score {total_score}/100{assumptions_note}). "
        f"Primary drivers: {days_overdue} days overdue ({comp_a_points} pts), "
        f"${invoice.outstanding_amount} outstanding balance ({comp_b_points} pts), "
        f"and {invoice.reminder_count} prior verified reminders ({comp_c_points} pts). "
        f"Recommended Action: '{action}'."
    )

    return InvoiceScoreResponse(
        invoice_id=invoice.invoice_id,
        status=status,
        is_actionable=True,
        days_overdue=days_overdue,
        score=total_score,
        priority=priority,
        contributing_factors=contributing_factors,
        recommended_action=action,
        action_reason=reason,
        unavailable_information=unavailable_info,
        explanation_summary=summary,
        scoring_version=SCORING_VERSION,
        evaluated_at=today,
    )
