from datetime import date, timedelta
from decimal import Decimal

from backend.recovery.models import InvoiceInput
from backend.recovery.strategies import evaluate_strategies

TODAY = date(2026, 11, 1)


class TestStrategyEvaluation:
    """Tests for the 4-strategy evaluation engine."""

    def test_newly_overdue_recommends_polite_reminder(self):
        """Newly overdue invoice (3 days, 0 reminders) recommends polite reminder."""
        inv = InvoiceInput(
            invoice_id="INV-STRAT-NEW",
            total_amount=Decimal("450.00"),
            outstanding_amount=Decimal("450.00"),
            currency="USD",
            status="OVERDUE",
            due_date=TODAY - timedelta(days=3),
            reminder_count=0,
            payment_history="on_time",
        )
        res = evaluate_strategies(inv, today=TODAY)
        assert res.recommended_strategy == "polite_reminder"
        assert len(res.strategies) == 4

        polite = next(s for s in res.strategies if s.strategy_id == "polite_reminder")
        assert polite.classification == "recommended"
        assert len(polite.advantages) > 0
        assert len(polite.limitations) > 0

    def test_moderately_overdue_recommends_firm_followup(self):
        """20 days overdue or 2 reminders recommends firm follow-up."""
        inv = InvoiceInput(
            invoice_id="INV-STRAT-FIRM",
            total_amount=Decimal("1200.00"),
            outstanding_amount=Decimal("1200.00"),
            currency="USD",
            status="OVERDUE",
            due_date=TODAY - timedelta(days=20),
            reminder_count=1,
            payment_history="on_time",
        )
        res = evaluate_strategies(inv, today=TODAY)
        assert res.recommended_strategy == "firm_follow_up"
        firm = next(s for s in res.strategies if s.strategy_id == "firm_follow_up")
        assert firm.classification == "recommended"

    def test_broken_promise_recommends_firm_followup(self):
        """Broken promise recommends firm follow-up and flags breach."""
        inv = InvoiceInput(
            invoice_id="INV-STRAT-BROKEN",
            total_amount=Decimal("800.00"),
            outstanding_amount=Decimal("800.00"),
            currency="USD",
            status="OVERDUE",
            due_date=TODAY - timedelta(days=12),
            reminder_count=1,
            has_promise_to_pay=True,
            promise_due_date=TODAY - timedelta(days=2),
        )
        res = evaluate_strategies(inv, today=TODAY)
        assert res.recommended_strategy == "firm_follow_up"
        firm = next(s for s in res.strategies if s.strategy_id == "firm_follow_up")
        assert firm.classification == "recommended"
        assert "missed" in firm.rationale.lower()

    def test_active_promise_recommends_scheduled_followup(self):
        """Active promise to pay in the future recommends scheduled follow-up."""
        inv = InvoiceInput(
            invoice_id="INV-STRAT-PROMISE",
            total_amount=Decimal("2000.00"),
            outstanding_amount=Decimal("2000.00"),
            currency="USD",
            status="OVERDUE",
            due_date=TODAY - timedelta(days=15),
            reminder_count=1,
            has_promise_to_pay=True,
            promise_due_date=TODAY + timedelta(days=3),
        )
        res = evaluate_strategies(inv, today=TODAY)
        assert res.recommended_strategy == "scheduled_follow_up"
        sched = next(s for s in res.strategies if s.strategy_id == "scheduled_follow_up")
        assert sched.classification == "recommended"
        polite = next(s for s in res.strategies if s.strategy_id == "polite_reminder")
        assert polite.classification == "not_recommended"

    def test_disputed_invoice_recommends_manual_review(self):
        """Disputed invoice escalates directly to manual account review."""
        inv = InvoiceInput(
            invoice_id="INV-STRAT-DISP",
            total_amount=Decimal("3000.00"),
            outstanding_amount=Decimal("3000.00"),
            currency="USD",
            status="DISPUTED",
            due_date=TODAY - timedelta(days=10),
            reminder_count=0,
        )
        res = evaluate_strategies(inv, today=TODAY)
        assert res.recommended_strategy == "manual_review"
        manual = next(s for s in res.strategies if s.strategy_id == "manual_review")
        assert manual.classification == "recommended"
        assert "dispute" in manual.rationale.lower()

    def test_repeated_reminders_escalates_to_manual_review(self):
        """3 or more reminders escalates to manual review."""
        inv = InvoiceInput(
            invoice_id="INV-STRAT-3REM",
            total_amount=Decimal("1500.00"),
            outstanding_amount=Decimal("1500.00"),
            currency="USD",
            status="OVERDUE",
            due_date=TODAY - timedelta(days=25),
            reminder_count=3,
        )
        res = evaluate_strategies(inv, today=TODAY)
        assert res.recommended_strategy == "manual_review"
        manual = next(s for s in res.strategies if s.strategy_id == "manual_review")
        assert manual.classification == "recommended"

    def test_all_strategies_have_factual_advantages_and_limitations_no_percentages(self):
        """Every strategy item contains non-empty advantages and limitations with zero invented percentages."""
        inv = InvoiceInput(
            invoice_id="INV-STRAT-FACTS",
            total_amount=Decimal("1000.00"),
            outstanding_amount=Decimal("1000.00"),
            currency="USD",
            status="OVERDUE",
            due_date=TODAY - timedelta(days=10),
            reminder_count=1,
        )
        res = evaluate_strategies(inv, today=TODAY)
        for s in res.strategies:
            assert s.advantages.strip(), f"Strategy {s.strategy_id} missing advantages"
            assert s.limitations.strip(), f"Strategy {s.strategy_id} missing limitations"
            assert "%" not in s.advantages, "Must not contain invented percentages"
            assert "%" not in s.limitations, "Must not contain invented percentages"
            assert "%" not in s.rationale, "Must not contain invented percentages"
