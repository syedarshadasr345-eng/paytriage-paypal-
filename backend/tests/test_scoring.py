from datetime import date, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from backend.recovery.actions import determine_next_best_action
from backend.recovery.config import SCORING_VERSION
from backend.recovery.models import (
    InvoiceInput,
)
from backend.recovery.scoring import calculate_recovery_score

# Fixed evaluation reference date for all deterministic tests
TODAY = date(2026, 11, 1)


class TestScoringEngineExclusionsAndSpecialCases:
    """Tests for excluded statuses, not-yet-due, and validation rules."""

    def test_not_yet_due_invoice(self):
        """Not-yet-due invoice (days_overdue <= 0) must not receive a score."""
        inv = InvoiceInput(
            invoice_id="INV-DUE-SOON",
            total_amount=Decimal("1000.00"),
            outstanding_amount=Decimal("1000.00"),
            currency="USD",
            status="SENT",
            due_date=TODAY + timedelta(days=5),
            reminder_count=0,
        )
        res = calculate_recovery_score(inv, today=TODAY)
        assert res.score is None
        assert res.priority is None
        assert res.is_actionable is False
        assert res.recommended_action == "wait"
        assert "not yet due" in res.action_reason.lower()

    @pytest.mark.parametrize("status,expected_action", [
        ("PAID", "no_action_required"),
        ("CANCELLED", "no_action_required"),
        ("DISPUTED", "manual_review"),
        ("DRAFT", "send_invoice"),
    ])
    def test_excluded_statuses(self, status, expected_action):
        """Paid, cancelled, disputed, and draft invoices must return score=None."""
        inv = InvoiceInput(
            invoice_id=f"INV-{status}",
            total_amount=Decimal("1500.00"),
            outstanding_amount=Decimal("1500.00"),
            currency="USD",
            status=status,
            due_date=TODAY - timedelta(days=10),
            reminder_count=0,
        )
        res = calculate_recovery_score(inv, today=TODAY)
        assert res.score is None
        assert res.priority is None
        assert res.is_actionable is False
        assert res.recommended_action == expected_action

    def test_unknown_status_fallback(self):
        """Unknown or unmapped status must return score=None and manual_review."""
        inv = InvoiceInput(
            invoice_id="INV-UNKNOWN",
            total_amount=Decimal("1000.00"),
            outstanding_amount=Decimal("1000.00"),
            currency="USD",
            status="ARCHIVED_UNRECOGNIZED",
            due_date=TODAY - timedelta(days=10),
            reminder_count=0,
        )
        res = calculate_recovery_score(inv, today=TODAY)
        assert res.score is None
        assert res.priority is None
        assert res.recommended_action == "manual_review"
        assert "unrecognized" in res.action_reason.lower()

    def test_partially_paid_is_actionable(self):
        """Partially paid invoices must be actionable and scored on outstanding balance."""
        inv = InvoiceInput(
            invoice_id="INV-PARTIAL",
            total_amount=Decimal("2000.00"),
            outstanding_amount=Decimal("600.00"),
            currency="USD",
            status="PARTIALLY_PAID",
            due_date=TODAY - timedelta(days=10),
            reminder_count=0,
            payment_history="on_time",
        )
        res = calculate_recovery_score(inv, today=TODAY)
        assert res.is_actionable is True
        # days 10 -> 20 pts; outstanding 600 -> 12 pts; reminders 0 -> 0; on_time -> 0. Total = 32
        assert res.score == 32
        assert res.priority == "MEDIUM"

    def test_promise_to_pay_missing_date_raises_validation_error(self):
        """has_promise_to_pay=True without promise_due_date must be rejected by Pydantic."""
        with pytest.raises(ValidationError):
            InvoiceInput(
                invoice_id="INV-INVALID-PROMISE",
                total_amount=Decimal("1000.00"),
                outstanding_amount=Decimal("1000.00"),
                currency="USD",
                status="OVERDUE",
                due_date=TODAY - timedelta(days=5),
                reminder_count=0,
                has_promise_to_pay=True,
                promise_due_date=None,
            )

    def test_negative_or_zero_amount_raises_validation_error(self):
        """Zero or negative amounts must fail validation."""
        with pytest.raises(ValidationError):
            InvoiceInput(
                invoice_id="INV-ZERO",
                total_amount=Decimal("0.00"),
                outstanding_amount=Decimal("0.00"),
                currency="USD",
                status="OVERDUE",
                due_date=TODAY - timedelta(days=5),
                reminder_count=0,
            )


class TestTableDrivenBoundaries:
    """Table-driven boundary tests for days overdue, amounts, and score priority bands."""

    @pytest.mark.parametrize("days_overdue,expected_days_pts", [
        (1, 10),
        (7, 10),
        (8, 20),
        (14, 20),
        (15, 30),
        (30, 30),
        (31, 40),
        (45, 40),
        (46, 40),
    ])
    def test_days_overdue_boundaries(self, days_overdue, expected_days_pts):
        """Verify exact point boundaries for days overdue (1/7, 8/14, 15/30, 31+)."""
        inv = InvoiceInput(
            invoice_id=f"INV-DAYS-{days_overdue}",
            total_amount=Decimal("400.00"), # 5 pts
            outstanding_amount=Decimal("400.00"),
            currency="USD",
            status="OVERDUE",
            due_date=TODAY - timedelta(days=days_overdue),
            reminder_count=0, # 0 pts
            payment_history="on_time", # 0 pts
        )
        res = calculate_recovery_score(inv, today=TODAY)
        assert res.score == expected_days_pts + 5

    @pytest.mark.parametrize("amount,expected_amount_pts", [
        (Decimal("499.99"), 5),
        (Decimal("500.00"), 12),
        (Decimal("1999.99"), 12),
        (Decimal("2000.00"), 18),
        (Decimal("4999.99"), 18),
        (Decimal("5000.00"), 25),
    ])
    def test_amount_boundaries(self, amount, expected_amount_pts):
        """Verify exact amount tier boundaries in USD ($499.99/500, $1999.99/2000, $4999.99/5000)."""
        inv = InvoiceInput(
            invoice_id=f"INV-AMT-{amount}",
            total_amount=amount,
            outstanding_amount=amount,
            currency="USD",
            status="OVERDUE",
            due_date=TODAY - timedelta(days=5), # 10 pts
            reminder_count=0, # 0 pts
            payment_history="on_time", # 0 pts
        )
        res = calculate_recovery_score(inv, today=TODAY)
        assert res.score == 10 + expected_amount_pts

    @pytest.mark.parametrize("days,amount,reminders,history,expected_score,expected_priority", [
        # LOW (< 25): 10 + 12 + 0 + 0 = 22
        (7, Decimal("500.00"), 0, "on_time", 22, "LOW"),
        # MEDIUM (25–49 boundary): 20 + 5 + 0 + 0 = 25
        (10, Decimal("400.00"), 0, "on_time", 25, "MEDIUM"),
        # MEDIUM upper edge: 30 + 18 + 0 + 0 = 48
        (15, Decimal("2000.00"), 0, "on_time", 48, "MEDIUM"),
        # HIGH (50–74): 30 + 18 + 6 + 0 = 54
        (15, Decimal("2000.00"), 1, "on_time", 54, "HIGH"),
        # CRITICAL (75–100 boundary): 40 + 18 + 12 + 5 = 75
        (35, Decimal("2000.00"), 2, None, 75, "CRITICAL"),
        # CRITICAL upper range: 40 + 25 + 6 + 15 = 86
        (35, Decimal("5000.00"), 1, "late", 86, "CRITICAL"),
    ])
    def test_priority_band_thresholds(self, days, amount, reminders, history, expected_score, expected_priority):
        """Verify priority classifications at critical thresholds."""
        inv = InvoiceInput(
            invoice_id="INV-BAND",
            total_amount=amount,
            outstanding_amount=amount,
            currency="USD",
            status="OVERDUE",
            due_date=TODAY - timedelta(days=days),
            reminder_count=reminders,
            payment_history=history,
        )
        res = calculate_recovery_score(inv, today=TODAY)
        assert res.score == expected_score
        assert res.priority == expected_priority

    @pytest.mark.parametrize("test_name,inv_kwargs,expected_score,expected_priority", [
        # Boundary 24 (LOW) vs 25 (MEDIUM)
        (
            "score_24_LOW",
            {
                "currency": "EUR",  # Non-USD: 0 amount pts
                "due_date": TODAY - timedelta(days=5),  # 10 pts (1-7 days)
                "reminder_count": 1,  # 6 pts
                "payment_history": "mixed",  # 8 pts -> 10 + 0 + 6 + 8 = 24
                "total_amount": Decimal("1000.00"),
                "outstanding_amount": Decimal("1000.00"),
            },
            24,
            "LOW",
        ),
        (
            "score_25_MEDIUM",
            {
                "currency": "USD",
                "due_date": TODAY - timedelta(days=10),  # 20 pts (8-14 days)
                "reminder_count": 0,  # 0 pts
                "payment_history": "on_time",  # 0 pts
                "total_amount": Decimal("400.00"),  # 5 pts (< $500) -> 20 + 5 + 0 + 0 = 25
                "outstanding_amount": Decimal("400.00"),
            },
            25,
            "MEDIUM",
        ),
        # Boundary 49 (MEDIUM) vs 50 (HIGH)
        (
            "score_49_MEDIUM",
            {
                "currency": "USD",
                "due_date": TODAY - timedelta(days=5),  # 10 pts (1-7 days)
                "reminder_count": 2,  # 12 pts
                "payment_history": "late",  # 15 pts
                "total_amount": Decimal("1000.00"),  # 12 pts ($500-$2000) -> 10 + 12 + 12 + 15 = 49
                "outstanding_amount": Decimal("1000.00"),
            },
            49,
            "MEDIUM",
        ),
        (
            "score_50_HIGH",
            {
                "currency": "USD",
                "due_date": TODAY - timedelta(days=15),  # 30 pts (15-30 days)
                "reminder_count": 0,  # 0 pts
                "payment_history": "mixed",  # 8 pts
                "total_amount": Decimal("1000.00"),  # 12 pts ($500-$2000) -> 30 + 12 + 0 + 8 = 50
                "outstanding_amount": Decimal("1000.00"),
            },
            50,
            "HIGH",
        ),
        # Boundary 74 (HIGH) vs 75 (CRITICAL)
        (
            "score_74_HIGH",
            {
                "currency": "USD",
                "due_date": TODAY - timedelta(days=35),  # 40 pts (>30 days)
                "reminder_count": 2,  # 12 pts
                "payment_history": "on_time",  # 0 pts
                "has_promise_to_pay": True,  # Broken promise: 10 pts (0 + 10 = 10 in D)
                "promise_due_date": TODAY - timedelta(days=2),
                "total_amount": Decimal("1000.00"),  # 12 pts ($500-$2000) -> 40 + 12 + 12 + 10 = 74
                "outstanding_amount": Decimal("1000.00"),
            },
            74,
            "HIGH",
        ),
        (
            "score_75_CRITICAL",
            {
                "currency": "USD",
                "due_date": TODAY - timedelta(days=35),  # 40 pts (>30 days)
                "reminder_count": 2,  # 12 pts
                "payment_history": None,  # Assumption: 5 pts
                "total_amount": Decimal("2500.00"),  # 18 pts ($2000-$5000) -> 40 + 18 + 12 + 5 = 75
                "outstanding_amount": Decimal("2500.00"),
            },
            75,
            "CRITICAL",
        ),
    ])
    def test_exact_priority_band_boundary_pairs(self, test_name, inv_kwargs, expected_score, expected_priority):
        """Strictly verify boundaries: 24 vs 25 (LOW/MEDIUM), 49 vs 50 (MEDIUM/HIGH), 74 vs 75 (HIGH/CRITICAL)."""
        inv = InvoiceInput(
            invoice_id=f"INV-BOUND-{test_name}",
            status="OVERDUE",
            **inv_kwargs,
        )
        res = calculate_recovery_score(inv, today=TODAY)
        assert res.score == expected_score, f"{test_name} failed score: expected {expected_score}, got {res.score}"
        assert res.priority == expected_priority, f"{test_name} failed priority: expected {expected_priority}, got {res.priority}"


class TestSpecialConditionsAndRules:
    """Tests for non-USD currencies, missing data, promises, and cooldowns."""

    def test_non_usd_currency_gives_zero_amount_points_and_labels_unavailable(self):
        """Non-USD currency assigns 0 points for Component B and adds unavailable notice."""
        inv = InvoiceInput(
            invoice_id="INV-EUR",
            total_amount=Decimal("10000.00"),
            outstanding_amount=Decimal("10000.00"),
            currency="EUR",
            status="OVERDUE",
            due_date=TODAY - timedelta(days=10), # 20 pts
            reminder_count=0, # 0 pts
            payment_history="on_time", # 0 pts
        )
        res = calculate_recovery_score(inv, today=TODAY)
        assert res.score == 20
        assert "amount_scoring_unavailable_for_currency" in res.unavailable_information
        # Check that Component B factor points is 0
        b_factors = [f for f in res.contributing_factors if "amount" in f.factor_name]
        assert len(b_factors) == 1
        assert b_factors[0].points == 0

    def test_missing_customer_history_has_assumption_flag(self):
        """Missing customer history applies 5 pt baseline marked as is_assumption=True."""
        inv = InvoiceInput(
            invoice_id="INV-MISSING-HIST",
            total_amount=Decimal("400.00"), # 5 pts
            outstanding_amount=Decimal("400.00"),
            currency="USD",
            status="OVERDUE",
            due_date=TODAY - timedelta(days=5), # 10 pts
            reminder_count=0,
            payment_history=None,
        )
        res = calculate_recovery_score(inv, today=TODAY)
        assert res.score == 20 # 10 + 5 + 0 + 5
        assert "customer_payment_history" in res.unavailable_information
        assumption_factors = [f for f in res.contributing_factors if f.is_assumption]
        assert len(assumption_factors) == 1
        assert assumption_factors[0].factor_name == "customer_history_unavailable"
        assert assumption_factors[0].points == 5

    def test_broken_promise_adds_10_pts_and_recommends_firm_followup(self):
        """Promise to pay date past due adds broken_promise factor and recommends firm follow-up."""
        inv = InvoiceInput(
            invoice_id="INV-BROKEN-PROMISE",
            total_amount=Decimal("600.00"), # 12 pts
            outstanding_amount=Decimal("600.00"),
            currency="USD",
            status="OVERDUE",
            due_date=TODAY - timedelta(days=10), # 20 pts
            reminder_count=1, # 6 pts
            payment_history="on_time", # 0 pts
            has_promise_to_pay=True,
            promise_due_date=TODAY - timedelta(days=2), # Broken promise (+10 pts)
        )
        res = calculate_recovery_score(inv, today=TODAY)
        # 20 (days) + 12 (amt) + 6 (rem) + 10 (broken promise) = 48
        assert res.score == 48
        assert res.recommended_action == "send_firm_followup"
        assert "committed to pay" in res.action_reason.lower() or "promise" in res.action_reason.lower()

    def test_active_promise_recommends_schedule_later_followup(self):
        """Active promise to pay (future date) recommends schedule_later_followup."""
        inv = InvoiceInput(
            invoice_id="INV-ACTIVE-PROMISE",
            total_amount=Decimal("600.00"),
            outstanding_amount=Decimal("600.00"),
            currency="USD",
            status="OVERDUE",
            due_date=TODAY - timedelta(days=10),
            reminder_count=1,
            payment_history="on_time",
            has_promise_to_pay=True,
            promise_due_date=TODAY + timedelta(days=4), # Active future commitment
        )
        res = calculate_recovery_score(inv, today=TODAY)
        assert res.recommended_action == "schedule_later_followup"
        assert str(TODAY + timedelta(days=4)) in res.action_reason

    def test_reminder_cooldown_recommends_wait_for_response(self):
        """If last reminder was sent < 3 days ago, recommend wait_for_response unless manual review."""
        inv = InvoiceInput(
            invoice_id="INV-COOLDOWN",
            total_amount=Decimal("600.00"),
            outstanding_amount=Decimal("600.00"),
            currency="USD",
            status="OVERDUE",
            due_date=TODAY - timedelta(days=5),
            reminder_count=1,
            last_reminder_date=TODAY - timedelta(days=1), # Sent 1 day ago (< 3 days)
            payment_history="on_time",
        )
        res = calculate_recovery_score(inv, today=TODAY)
        assert res.recommended_action == "wait_for_response"
        assert "cooldown" in res.action_reason.lower()

    def test_three_reminders_escalates_to_manual_review_overriding_cooldown(self):
        """3+ reminders triggers manual review, even if cooldown date is recent."""
        inv = InvoiceInput(
            invoice_id="INV-REPEAT-REMINDERS",
            total_amount=Decimal("600.00"),
            outstanding_amount=Decimal("600.00"),
            currency="USD",
            status="OVERDUE",
            due_date=TODAY - timedelta(days=20),
            reminder_count=3,
            last_reminder_date=TODAY - timedelta(days=1), # Cooldown would apply if not for 3 reminders
            payment_history="on_time",
        )
        res = calculate_recovery_score(inv, today=TODAY)
        assert res.recommended_action == "manual_review"

    def test_determinism_same_input_twice_gives_identical_output(self):
        """Deterministic pure function: identical inputs must yield 100% identical responses."""
        inv = InvoiceInput(
            invoice_id="INV-DETERMINISM",
            total_amount=Decimal("3500.00"),
            outstanding_amount=Decimal("3500.00"),
            currency="USD",
            status="OVERDUE",
            due_date=TODAY - timedelta(days=22),
            reminder_count=2,
            payment_history="mixed",
        )
        res1 = calculate_recovery_score(inv, today=TODAY)
        res2 = calculate_recovery_score(inv, today=TODAY)
        assert res1.model_dump() == res2.model_dump()


class TestWorkedExamplesFromSpec:
    """The three worked examples documented in docs/SCORING.md."""

    def test_example_1_severely_overdue_high_value(self):
        """Example 1: Amount $7500, 35 days, 2 reminders, mixed history -> Score 85, CRITICAL."""
        inv = InvoiceInput(
            invoice_id="INV-EX1",
            total_amount=Decimal("7500.00"),
            outstanding_amount=Decimal("7500.00"),
            currency="USD",
            status="OVERDUE",
            due_date=TODAY - timedelta(days=35), # 40 pts
            reminder_count=2, # 12 pts
            payment_history="mixed", # 8 pts
        )
        res = calculate_recovery_score(inv, today=TODAY)
        # 40 + 25 (amount >= 5000) + 12 + 8 = 85
        assert res.score == 85
        assert res.priority == "CRITICAL"
        assert res.recommended_action == "send_firm_followup"
        assert res.scoring_version == SCORING_VERSION

    def test_example_2_newly_overdue_low_value(self):
        """Example 2: Amount $350, 3 days, 0 reminders, on-time history -> Score 15, LOW."""
        inv = InvoiceInput(
            invoice_id="INV-EX2",
            total_amount=Decimal("350.00"),
            outstanding_amount=Decimal("350.00"),
            currency="USD",
            status="OVERDUE",
            due_date=TODAY - timedelta(days=3), # 10 pts
            reminder_count=0, # 0 pts
            payment_history="on_time", # 0 pts
        )
        res = calculate_recovery_score(inv, today=TODAY)
        # 10 + 5 (amount < 500) + 0 + 0 = 15
        assert res.score == 15
        assert res.priority == "LOW"
        assert res.recommended_action == "send_polite_reminder"

    def test_example_3_missing_history_account(self):
        """Example 3: Amount $1500, 10 days, 1 reminder, missing history -> Score 43, MEDIUM."""
        inv = InvoiceInput(
            invoice_id="INV-EX3",
            total_amount=Decimal("1500.00"),
            outstanding_amount=Decimal("1500.00"),
            currency="USD",
            status="OVERDUE",
            due_date=TODAY - timedelta(days=10), # 20 pts
            reminder_count=1, # 6 pts
            payment_history=None, # 5 pts assumption
        )
        res = calculate_recovery_score(inv, today=TODAY)
        # 20 + 12 (amount 500-2000) + 6 + 5 = 43
        assert res.score == 43
        assert res.priority == "MEDIUM"
        assert res.recommended_action == "send_polite_reminder"
        assert "customer_payment_history" in res.unavailable_information


class TestSeededInvoicesScoreRegression:
    """Regression tests pinning the exact expected scores for all benchmark demo invoices."""

    EXPECTED_SCORES = {
        "INV-PAID-001": (None, None),
        "INV-CANCELLED-002": (None, None),
        "INV-DISPUTED-003": (None, None),
        "INV-DRAFT-004": (None, None),
        "INV-NOTDUE-005": (None, None),
        "INV-NEW-006": (15, "LOW"),
        "INV-MOD-007": (38, "MEDIUM"),
        "INV-HIGH-008": (68, "HIGH"),
        "INV-SEV-009": (92, "CRITICAL"),
        "INV-REPEAT-010": (62, "HIGH"),
        "INV-NOHIST-011": (43, "MEDIUM"),
        "INV-PARTIAL-012": (54, "HIGH"),
        "INV-BROKEN-013": (53, "HIGH"),
        "INV-PROMISE-014": (44, "MEDIUM"),
        "INV-COOLDOWN-015": (38, "MEDIUM"),
        "INV-NONUSD-016": (26, "MEDIUM"),
    }

    def test_all_seeded_invoices_expected_scores(self):
        """Pin scores and priorities for all 16 seed demo invoices evaluated at reference date TODAY."""
        from backend.recovery.router import invoice_dict_to_input
        from backend.seed import get_seed_invoices

        seed_invoices = get_seed_invoices(base_date=TODAY)
        assert len(seed_invoices) == 16, f"Expected 16 seed invoices, got {len(seed_invoices)}"

        for raw_inv in seed_invoices:
            inv_id = raw_inv["id"]
            expected_score, expected_priority = self.EXPECTED_SCORES[inv_id]
            inv_input = invoice_dict_to_input(raw_inv)
            res = calculate_recovery_score(inv_input, today=TODAY)

            assert res.score == expected_score, (
                f"{inv_id}: expected score {expected_score}, got {res.score}. "
                f"Factors: {[(f.factor_name, f.points) for f in res.contributing_factors]}"
            )
            assert res.priority == expected_priority, (
                f"{inv_id}: expected priority {expected_priority}, got {res.priority}"
            )

    def test_inv_mod_007_exact_factor_breakdown(self):
        """INV-MOD-007 breakdown: 20 (days) + 12 (amount) + 6 (1 reminder) + 0 (on_time history) = 38."""
        from backend.recovery.router import invoice_dict_to_input
        from backend.seed import get_seed_invoices

        seed_map = {inv["id"]: inv for inv in get_seed_invoices(base_date=TODAY)}
        inv_007 = invoice_dict_to_input(seed_map["INV-MOD-007"])
        res = calculate_recovery_score(inv_007, today=TODAY)

        factor_dict = {f.factor_name: f.points for f in res.contributing_factors}
        assert factor_dict["moderately_overdue"] == 20
        assert factor_dict["amount_medium"] == 12
        assert factor_dict["single_unanswered_reminder"] == 6
        assert factor_dict["customer_history_good"] == 0
        assert res.score == 38
        assert res.priority == "MEDIUM"

    def test_reminder_grammar_singular_vs_plural(self):
        """Action reason must say '1 prior follow-up' (singular) vs 'X prior follow-ups' (plural)."""

        inv_1 = InvoiceInput(
            invoice_id="INV-G1",
            total_amount=Decimal(500),
            outstanding_amount=Decimal(500),
            status="SENT",
            due_date=TODAY - timedelta(days=10),
            reminder_count=1,
        )
        _, reason_1 = determine_next_best_action(inv_1, TODAY)
        assert "1 prior follow-up." in reason_1
        assert "1 prior follow-ups" not in reason_1

        inv_2 = InvoiceInput(
            invoice_id="INV-G2",
            total_amount=Decimal(500),
            outstanding_amount=Decimal(500),
            status="SENT",
            due_date=TODAY - timedelta(days=5),
            reminder_count=0,
        )
        _, reason_2 = determine_next_best_action(inv_2, TODAY)
        assert "0 prior follow-ups." in reason_2
