from datetime import date

from backend.recovery.models import InvoiceInput, StrategyEvaluation, StrategyItem


def evaluate_strategies(invoice: InvoiceInput, today: date | None = None) -> StrategyEvaluation:
    """
    Evaluates recovery strategies for an invoice against verified facts.
    Pure logic: no network calls, no AI, no invented percentages.
    
    Strategies evaluated:
    - polite_reminder (Polite Payment Reminder)
    - firm_follow_up (Firm Direct Follow-up)
    - scheduled_follow_up (Scheduled Follow-up)
    - manual_review (Manual Review & Escalation)
    """
    if today is None:
        today = date.today()

    days_overdue = (today - invoice.due_date).days
    status = invoice.status.upper()
    reminder_count = invoice.reminder_count
    has_active_promise = invoice.has_promise_to_pay and invoice.promise_due_date is not None and invoice.promise_due_date >= today
    has_broken_promise = invoice.has_promise_to_pay and invoice.promise_due_date is not None and invoice.promise_due_date < today

    strategies: list[StrategyItem] = []

    # 1. Polite Reminder
    if status in ["PAID", "CANCELLED", "DISPUTED", "DRAFT"]:
        polite_class = "not_recommended"
        polite_rationale = f"Invoice status is {status}. Standard polite reminder is not appropriate."
    elif days_overdue <= 0:
        polite_class = "not_recommended"
        polite_rationale = "Invoice is not yet due. Outreach should wait until maturity."
    elif reminder_count >= 3 or days_overdue > 45:
        polite_class = "not_recommended"
        polite_rationale = f"Invoice has {reminder_count} reminders and is {days_overdue} days overdue. Polite messaging has proven insufficient."
    elif has_broken_promise:
        polite_class = "not_recommended"
        polite_rationale = "Debtor missed a confirmed payment commitment date. A soft reminder lacks necessary urgency."
    elif has_active_promise:
        polite_class = "not_recommended"
        polite_rationale = f"Active commitment to pay on {invoice.promise_due_date} is on file. Stand down until commitment date."
    elif days_overdue <= 14 and reminder_count <= 1:
        polite_class = "recommended"
        polite_rationale = f"Invoice is newly overdue ({days_overdue} days) with {reminder_count} prior reminder(s). Preserves commercial goodwill."
    else:
        polite_class = "applicable"
        polite_rationale = "Can be used as a secondary touchpoint, though delinquency suggests more direct communication."

    strategies.append(StrategyItem(
        strategy_id="polite_reminder",
        name="Polite Payment Reminder",
        classification=polite_class,
        rationale=polite_rationale,
        advantages="Preserves customer relationship; non-adversarial; lowest friction for legitimate oversights.",
        limitations="Less effective for chronic or intentional late payers; creates lower urgency for prompt settlement."
    ))

    # 2. Firm Follow-up
    if status in ["PAID", "CANCELLED", "DISPUTED", "DRAFT"]:
        firm_class = "not_recommended"
        firm_rationale = f"Invoice status is {status}. Firm recovery communication is not permitted."
    elif days_overdue <= 0:
        firm_class = "not_recommended"
        firm_rationale = "Invoice is not yet due. Firm demands prior to due date violate customer terms."
    elif has_active_promise:
        firm_class = "not_recommended"
        firm_rationale = f"Active promise to pay on {invoice.promise_due_date} is in place. Premature firm follow-up harms trust."
    elif has_broken_promise:
        firm_class = "recommended"
        firm_rationale = f"Customer missed promised payment date ({invoice.promise_due_date}). Firm follow-up is necessary to enforce commitment."
    elif (days_overdue > 14 or reminder_count == 2) and days_overdue <= 45 and reminder_count < 3:
        firm_class = "recommended"
        firm_rationale = f"Delinquency has reached {days_overdue} days with {reminder_count} prior reminder(s). Clear, firm communication is required."
    elif days_overdue > 45 or reminder_count >= 3:
        firm_class = "applicable"
        firm_rationale = "May be attempted as final written notice, but account primarily warrants manual review escalation."
    else:
        firm_class = "applicable"
        firm_rationale = "Available if invoice balance is large or previous relationships suggest early firmness, but polite tone is preferred."

    strategies.append(StrategyItem(
        strategy_id="firm_follow_up",
        name="Firm Direct Follow-up",
        classification=firm_class,
        rationale=firm_rationale,
        advantages="Clearly highlights contractual payment obligations and urgency; prompts decisive debtor action.",
        limitations="More assertive tone carries friction risk; may strain sensitive business relationships if misapplied."
    ))

    # 3. Scheduled Later Follow-up
    if status in ["PAID", "CANCELLED"]:
        sched_class = "not_recommended"
        sched_rationale = f"Invoice is {status}. No scheduled follow-up is required."
    elif has_active_promise:
        sched_class = "recommended"
        sched_rationale = f"Customer explicitly promised payment by {invoice.promise_due_date}. Scheduled follow-up honors this agreed date."
    elif days_overdue <= 0:
        sched_class = "applicable"
        sched_rationale = f"Can be scheduled to follow up immediately after due date ({invoice.due_date}) if unpaid."
    elif has_broken_promise:
        sched_class = "not_recommended"
        sched_rationale = "Debtor already breached payment commitment date. Further postponement delays necessary action."
    elif days_overdue > 30 or reminder_count >= 2:
        sched_class = "not_recommended"
        sched_rationale = "Significant aging or multiple unanswered reminders indicate scheduling delays will increase default risk."
    else:
        sched_class = "applicable"
        sched_rationale = "Can be scheduled if customer has requested a short verified extension or pending billing cycle."

    strategies.append(StrategyItem(
        strategy_id="scheduled_follow_up",
        name="Scheduled Later Follow-up",
        classification=sched_class,
        rationale=sched_rationale,
        advantages="Honors agreed customer commitment; prevents redundant outreach and customer annoyance.",
        limitations="Postpones active collections; relies entirely on counterparty honoring stated commitment."
    ))

    # 4. Manual Review Escalation
    if status == "DISPUTED":
        manual_class = "recommended"
        manual_rationale = "Invoice is in active dispute. Automated collection must stop and account requires human mediation."
    elif status in ["PAID", "CANCELLED"]:
        manual_class = "not_recommended"
        manual_rationale = f"Invoice is {status}. No manual escalation needed."
    elif days_overdue > 45 or reminder_count >= 3:
        manual_class = "recommended"
        manual_rationale = f"High delinquency ({days_overdue} days) or repeated unsuccessful reminders ({reminder_count}) requires personal staff intervention."
    elif invoice.outstanding_amount >= 5000:
        manual_class = "applicable"
        manual_rationale = "High financial exposure ($5,000+). Manual review can be conducted to evaluate phone outreach or customized terms."
    elif days_overdue <= 0 or status == "DRAFT":
        manual_class = "not_recommended"
        manual_rationale = "Routine pre-due or draft invoice does not justify merchant manual staff review."
    else:
        manual_class = "not_recommended"
        manual_rationale = "Invoice is in routine overdue stages (1–14 days) and can be handled via standard automated communication."

    strategies.append(StrategyItem(
        strategy_id="manual_review",
        name="Manual Account Escalation",
        classification=manual_class,
        rationale=manual_rationale,
        advantages="Facilitates direct human negotiation, custom payment plans, dispute mediation, or executive escalation.",
        limitations="Consumes merchant staff time and operational bandwidth; cannot be automated at scale."
    ))

    # Determine recommended_strategy ID
    recommended_candidates = [s.strategy_id for s in strategies if s.classification == "recommended"]
    if recommended_candidates:
        primary_recommended = recommended_candidates[0]
    else:
        # Fallback if none explicitly marked recommended (e.g., settled/cancelled)
        primary_recommended = "none"

    return StrategyEvaluation(
        invoice_id=invoice.invoice_id,
        recommended_strategy=primary_recommended,
        strategies=strategies
    )
