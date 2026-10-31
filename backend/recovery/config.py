from decimal import Decimal

# Scoring Engine Configuration & Version Metadata
SCORING_VERSION = "1.0.0"

# Operational Rules & Cooldowns
REMINDER_COOLDOWN_DAYS = 3
MAX_FOLLOWUPS_BEFORE_MANUAL_REVIEW = 3
SEVERE_DELINQUENCY_DAYS = 45

# Component A: Days Overdue Weights (Max 40 points)
DAYS_OVERDUE_WEIGHTS = [
    {"min_days": 1, "max_days": 7, "points": 10, "factor": "newly_overdue", "description": "Invoice is newly overdue (1–7 days)."},
    {"min_days": 8, "max_days": 14, "points": 20, "factor": "moderately_overdue", "description": "Invoice is moderately overdue (8–14 days)."},
    {"min_days": 15, "max_days": 30, "points": 30, "factor": "significantly_overdue", "description": "Invoice is significantly overdue (15–30 days)."},
    {"min_days": 31, "max_days": None, "points": 40, "factor": "severely_overdue", "description": "Invoice is severely overdue (> 30 days). High operational concern."},
]

# Component B: Outstanding Amount Weights (USD only, Max 25 points)
AMOUNT_WEIGHTS_USD = [
    {"min_amount": Decimal("0.01"), "max_amount": Decimal("499.99"), "points": 5, "factor": "amount_low", "description": "Outstanding balance under $500. Lower balance risk."},
    {"min_amount": Decimal("500.00"), "max_amount": Decimal("1999.99"), "points": 12, "factor": "amount_medium", "description": "Moderate balance exposure ($500 to $1,999.99)."},
    {"min_amount": Decimal("2000.00"), "max_amount": Decimal("4999.99"), "points": 18, "factor": "amount_high", "description": "Substantial balance ($2,000 to $4,999.99)."},
    {"min_amount": Decimal("5000.00"), "max_amount": None, "points": 25, "factor": "amount_critical", "description": "High balance exposure (>= $5,000.00). Significant capital impact."},
]

# Component C: Reminder History Weights (Max 20 points)
REMINDER_COUNT_WEIGHTS = {
    0: {"points": 0, "factor": "no_reminders", "description": "No prior verified follow-ups dispatched."},
    1: {"points": 6, "factor": "single_unanswered_reminder", "description": "1 prior verified reminder delivered with no payment."},
    2: {"points": 12, "factor": "multiple_unanswered_reminders", "description": "2 prior verified reminders delivered with no payment."},
    3: {"points": 20, "factor": "repeated_unsuccessful_reminders", "description": "3+ prior follow-ups delivered without settlement."},
}

# Component D: Customer History & Risk Signals (Max 15 points)
COMPONENT_D_MAX_POINTS = 15
PAYMENT_HISTORY_POINTS = {
    "late": {"points": 15, "factor": "customer_history_late", "description": "Documented record of repeated late payments."},
    "mixed": {"points": 8, "factor": "customer_history_mixed", "description": "Mixed historical record of on-time and late payments."},
    "on_time": {"points": 0, "factor": "customer_history_good", "description": "Consistent on-time payment track record."},
}
CUSTOMER_HISTORY_MISSING_POINTS = 5
BROKEN_PROMISE_POINTS = 10

# Priority Bands
PRIORITY_BANDS = [
    {"min_score": 75, "max_score": 100, "priority": "CRITICAL"},
    {"min_score": 50, "max_score": 74, "priority": "HIGH"},
    {"min_score": 25, "max_score": 49, "priority": "MEDIUM"},
    {"min_score": 0, "max_score": 24, "priority": "LOW"},
]
