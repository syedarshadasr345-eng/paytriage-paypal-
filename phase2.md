# PHASE 2 — Core Recovery Intelligence

> First read `RULES.md`. Phase 1 must be approved. Do not touch AI or PayPal code in this phase.

## Goal
Build the deterministic, explainable recovery engine: score, priority, next-best-action, and strategy comparison. **Pure logic with no network calls and no AI.**

## Step 1 — Write the spec first (no code yet)
Create `docs/SCORING.md` and show it to me for approval before coding. It must define:

- Inputs (only verified fields): amount, due date, days overdue, status, reminder count, previous outcomes, payment history (optional).
- Score range 0–100 and the exact point rules.
- Suggested starting weights (adjust if the existing data model requires):
  - Days overdue: up to 40 points
  - Invoice amount: up to 25 points
  - Reminder history / unsuccessful follow-ups: up to 20 points
  - Status and other verified signals: up to 15 points
- Priority bands: Critical, High, Medium, Low (state the exact thresholds).
- Excluded statuses: paid, cancelled, disputed, draft → no ordinary score; state what is returned instead.
- Missing-data behavior: never invent values; mark them "unavailable" and state how that affects the score.
- Disclaimer: this is a decision-support priority score, not a payment-probability prediction.

**Wait for my approval of the spec.**

## Step 2 — Tests first
Write tests before implementation. Cover:

- Paid invoice
- Cancelled invoice
- Disputed invoice
- Newly overdue invoice (1–3 days)
- Moderately overdue invoice
- Severely overdue invoice
- Not yet due invoice
- Missing customer history
- Repeated unsuccessful reminders → manual review
- Boundary values at every priority threshold
- Large and small amounts (use Decimal or integer cents; no floats)
- Same input always gives the same output (determinism)

## Step 3 — Implement
- `recovery/scoring.py`: returns score, priority, list of contributing factors (name, points, reason), and a plain-language explanation.
- `recovery/actions.py`: next-best-action rules with a reason for each result (see RULES.md §5.3).
- `recovery/strategies.py`: compare polite reminder, firm follow-up, scheduled follow-up, manual review. Advantages and limitations only. No invented percentages.
- Use Pydantic models for inputs and outputs.
- Add endpoints (adapt to the existing backend structure):
  - `GET /api/recovery/queue` — prioritized list, with filter and sort parameters
  - `GET /api/recovery/invoices/{id}` — score, factors, recommended action, reason
  - `GET /api/recovery/invoices/{id}/strategies`
- Enforce invoice ownership checks if authentication exists.
- Every number returned comes from backend data, not hardcoded values.

## Step 4 — Run tests
Run the full test suite. Paste the real output. Fix failures at the root cause.

## End-of-phase report (required)
1. What was implemented
2. Files changed
3. What works
4. Tests performed and actual results (pasted output)
5. Remaining issues
6. What needs my approval next

End with: "Phase 2 complete. Awaiting your approval before Phase 3."
