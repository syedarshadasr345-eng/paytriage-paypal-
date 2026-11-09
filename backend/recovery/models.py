from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from pydantic import BaseModel, Field, model_validator


class ContributingFactor(BaseModel):
    factor_name: str
    points: int
    description: str
    is_assumption: bool = False


class InvoiceInput(BaseModel):
    invoice_id: str
    customer_name: str = "Customer"
    customer_email: str | None = None
    total_amount: Decimal
    outstanding_amount: Decimal
    currency: str = "USD"
    status: str
    due_date: date
    reminder_count: int = Field(default=0, ge=0)
    last_reminder_date: date | None = None
    payment_history: str | None = None  # "on_time", "mixed", "late", or None
    has_promise_to_pay: bool = False
    promise_due_date: date | None = None

    @model_validator(mode="after")
    def validate_amounts_and_promise(self) -> "InvoiceInput":
        # Amount must be strictly positive
        if self.total_amount <= Decimal("0.00"):
            raise ValueError("total_amount must be greater than zero.")
        if self.outstanding_amount <= Decimal("0.00"):
            raise ValueError("outstanding_amount must be greater than zero.")
        if self.outstanding_amount > self.total_amount:
            raise ValueError("outstanding_amount cannot exceed total_amount.")

        # Quantize to 2 decimals
        self.total_amount = self.total_amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        self.outstanding_amount = self.outstanding_amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        # Validate promise to pay consistency
        if self.has_promise_to_pay and self.promise_due_date is None:
            raise ValueError("promise_due_date is required when has_promise_to_pay is True.")

        # Status normalization
        self.status = self.status.strip().upper()
        if self.currency:
            self.currency = self.currency.strip().upper()

        return self


class InvoiceScoreResponse(BaseModel):
    invoice_id: str
    status: str
    is_actionable: bool
    days_overdue: int
    score: int | None = None
    priority: str | None = None
    contributing_factors: list[ContributingFactor] = []
    recommended_action: str
    action_reason: str
    unavailable_information: list[str] = []
    explanation_summary: str
    scoring_version: str
    evaluated_at: date


class StrategyItem(BaseModel):
    strategy_id: str
    name: str
    classification: str  # "recommended" | "applicable" | "not_recommended"
    rationale: str
    advantages: str
    limitations: str


class StrategyEvaluation(BaseModel):
    invoice_id: str
    recommended_strategy: str
    strategies: list[StrategyItem]
