from datetime import date

from backend.recovery.config import (
    MAX_FOLLOWUPS_BEFORE_MANUAL_REVIEW,
    REMINDER_COOLDOWN_DAYS,
    SEVERE_DELINQUENCY_DAYS,
)
from backend.recovery.models import InvoiceInput

RECOGNIZED_STATUSES = {"DRAFT", "SENT", "OVERDUE", "PARTIALLY_PAID", "PAID", "CANCELLED", "DISPUTED"}


def determine_next_best_action(invoice: InvoiceInput, today: date) -> tuple[str, str]:
    """
    Deterministically computes the next-best recovery action and its visible reason.
    Evaluates strictly against the supplied 'today' date.
    Returns (action_code, action_reason).
    """
    status = invoice.status.upper()

    # 1. Unrecognized Status
    if status not in RECOGNIZED_STATUSES:
        return (
            "manual_review",
            f"Unrecognized invoice status '{status}'. Manual review required to determine account standing."
        )

    # 2. Excluded Settled / Cancelled
    if status in ("PAID", "CANCELLED"):
        return (
            "no_action_required",
            f"Invoice is {status.lower()}. No recovery action required."
        )

    # 3. Disputed
    if status == "DISPUTED":
        return (
            "manual_review",
            "Invoice is currently under dispute. Automated recovery outreach is suspended pending manual dispute resolution."
        )

    # 4. Draft
    if status == "DRAFT":
        return (
            "send_invoice",
            "Invoice is in draft mode and has not yet been issued to the customer."
        )

    # Calculate days overdue relative to provided reference date
    days_overdue = (today - invoice.due_date).days

    # 5. Not Yet Due
    if days_overdue <= 0:
        return (
            "wait",
            f"Invoice is not yet due (due on {invoice.due_date})."
        )

    # 6. Escalation to Manual Review (overrides cooldown and active outreach)
    if invoice.reminder_count >= MAX_FOLLOWUPS_BEFORE_MANUAL_REVIEW or days_overdue > SEVERE_DELINQUENCY_DAYS:
        return (
            "manual_review",
            f"Repeated follow-ups ({invoice.reminder_count}) or severe delinquency ({days_overdue} days overdue) "
            f"require human account review rather than automated notifications."
        )

    # 7. Broken Promise to Pay
    if invoice.has_promise_to_pay and invoice.promise_due_date and invoice.promise_due_date < today:
        return (
            "send_firm_followup",
            f"Customer committed to pay by {invoice.promise_due_date}, but balance remains unpaid. "
            f"Immediate firm follow-up required regarding the broken commitment."
        )

    # 8. Active Promise to Pay
    if invoice.has_promise_to_pay and invoice.promise_due_date and invoice.promise_due_date >= today:
        return (
            "schedule_later_followup",
            f"Customer committed to pay on {invoice.promise_due_date}. Follow up on the agreed commitment date."
        )

    # 9. Reminder Cooldown Guard (if last reminder was delivered < REMINDER_COOLDOWN_DAYS ago)
    if invoice.last_reminder_date is not None:
        days_since_reminder = (today - invoice.last_reminder_date).days
        if 0 <= days_since_reminder < REMINDER_COOLDOWN_DAYS:
            return (
                "wait_for_response",
                f"Reminder delivered on {invoice.last_reminder_date}. Cooldown period active "
                f"({days_since_reminder} of {REMINDER_COOLDOWN_DAYS} days elapsed). Wait for customer response before follow-up."
            )

    # 10. Firm Follow-up Progression (15–45 days overdue or 2 prior reminders delivered)
    if days_overdue > 14 or invoice.reminder_count == 2:
        if days_overdue > 14 and invoice.reminder_count >= 2:
            reason = f"Invoice is significantly overdue ({days_overdue} days) and prior reminders ({invoice.reminder_count}) yielded no payment. A firm follow-up is required."
        elif days_overdue > 14:
            reason = f"Invoice is significantly overdue ({days_overdue} days). A firm follow-up is required."
        else:
            reason = f"Prior polite reminders ({invoice.reminder_count}) yielded no payment. A firm follow-up is required."
        return ("send_firm_followup", reason)

    # 11. Polite Reminder (Default for 1–14 days overdue with 0–1 prior follow-ups)
    overdue_desc = "newly overdue" if days_overdue <= 7 else "moderately overdue"
    followup_str = "1 prior follow-up" if invoice.reminder_count == 1 else f"{invoice.reminder_count} prior follow-ups"
    return (
        "send_polite_reminder",
        f"Invoice is {overdue_desc} ({days_overdue} days) with {followup_str}. "
        f"A polite payment reminder preserves the customer relationship while prompting settlement."
    )
