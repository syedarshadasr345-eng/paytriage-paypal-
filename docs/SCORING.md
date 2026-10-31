# SCORING.md — Adaptive Recovery Intelligence Specification

> **Version:** 1.0.0  
> **Status:** Approved Specification (incorporating user amendments)  
> **Target System:** InvoicePilot AI — Decision-Support Recovery Engine  
> **Rule Compliance:** Strictly conforms to `RULES.md` (§5, §9, §11) and `phase2.md`

---

## 1. Purpose and Disclaimer

### 1.1 Purpose
The InvoicePilot AI Recovery Scoring Engine is a deterministic, fully explainable decision-support system. It computes a priority score ($0$ to $100$) for overdue and partially paid invoices to help businesses determine:
1. Which invoices require attention first.
2. Why an invoice is categorized as urgent or at risk.
3. What next-best recovery action is recommended, supported by documented rules and verified data.

### 1.2 Mandatory Disclaimer
> **IMPORTANT:**  
> The Recovery Score is a **decision-support priority score**, NOT a statistically validated probability prediction or a guarantee of payment recovery. It reflects operational urgency based strictly on verified invoice facts and business rules.

---

## 2. Inputs & Data Types

The scoring engine operates **only on verified fields** supplied to the pure function. It takes an explicit evaluation date (`today: datetime.date`) and **never reads the system clock inside the scoring logic**.

| Field Name | Type | Constraints / Verification | Description |
| :--- | :--- | :--- | :--- |
| `invoice_id` | `str` | Non-empty unique identifier | Backend invoice identifier |
| `total_amount` | `Decimal` | $> 0$, quantized to 2 decimals | Original invoice total |
| `outstanding_amount` | `Decimal` | $> 0$, $\le \text{total\_amount}$, quantized to 2 decimals | Current unpaid balance (scored balance) |
| `currency` | `str` | ISO 4217 (e.g., `"USD"`) | Currency code. Amount thresholds apply to USD only. |
| `status` | `str` | `DRAFT`, `SENT`, `OVERDUE`, `PARTIALLY_PAID`, `PAID`, `CANCELLED`, `DISPUTED` | Current verified status |
| `due_date` | `datetime.date` | Valid ISO date | Payment due date |
| `reminder_count` | `int` | $\ge 0$ | Verified count of previously dispatched and delivered reminders (never drafts or copied) |
| `last_reminder_date` | `Optional[datetime.date]` | Valid date if `reminder_count > 0` | Date of most recent verified reminder |
| `payment_history`| `Optional[str]` | `"on_time"`, `"mixed"`, `"late"`, or `None` | Verified historical payment behavior if available |
| `has_promise_to_pay` | `bool` | Verified active commitment | Whether debtor agreed to a specific payment date |
| `promise_due_date` | `Optional[datetime.date]` | Required if `has_promise_to_pay` is True | Promised payment date (validation error if missing when `has_promise_to_pay` is True) |

---

## 3. Excluded Statuses & Not-Yet-Due Handling

Certain invoice statuses and conditions are excluded from receiving a standard 0–100 recovery score:

| Status / Condition | Score | Priority | Recommended Action | Stated Reason |
| :--- | :---: | :---: | :--- | :--- |
| `days_overdue <= 0` (Not yet due) | `None` (`null`) | `None` | `wait` | Invoice is not yet due. |
| `PAID` | `None` (`null`) | `None` | `no_action_required` | Invoice is fully settled. No recovery action required. |
| `CANCELLED` | `None` (`null`) | `None` | `no_action_required` | Invoice was cancelled by the merchant. Do not send reminders. |
| `DISPUTED` | `None` (`null`) | `None` | `manual_review` | Invoice is under dispute. Automated recovery suspended pending manual resolution. |
| `DRAFT` | `None` (`null`) | `None` | `send_invoice` | Invoice is in draft mode and has not yet been issued to customer. |
| *Unknown / Unmapped Status* | `None` (`null`) | `None` | `manual_review` | Unrecognized invoice status. Manual review required. |

> **Queue Behavior:** By default, invoices with `days_overdue <= 0` (not yet due) and excluded statuses are filtered out of `/api/recovery/queue`. An optional query parameter `include_not_due=true` allows viewing not-yet-due invoices in the queue with status `wait`.

---

## 4. Score Calculation (0 to 100 Points)

For actionable invoices (`OVERDUE` or `PARTIALLY_PAID` with `days_overdue > 0`), the score is computed as:

$$\text{Total Score} = \text{Points}_{\text{DaysOverdue}} + \text{Points}_{\text{Amount}} + \text{Points}_{\text{Reminders}} + \text{Points}_{\text{RiskSignals}}$$

Total points are clamped to $[0, 100]$.

### 4.1 Component A: Days Overdue (Weight: Up to 40 Points)
Calculated strictly against the provided `today` parameter: $\text{days\_overdue} = (\text{today} - \text{due\_date}).\text{days}$.

| Condition | Points | Factor Name | Factor Description |
| :--- | :---: | :--- | :--- |
| `1 <= days_overdue <= 7` | 10 | `newly_overdue` | Invoice is newly overdue (1–7 days). |
| `8 <= days_overdue <= 14` | 20 | `moderately_overdue` | Invoice is 8–14 days overdue. |
| `15 <= days_overdue <= 30` | 30 | `significantly_overdue` | Invoice is 15–30 days overdue. |
| `days_overdue > 30` | 40 | `severely_overdue` | Invoice is severely overdue (> 30 days). High operational concern. |

*(Note: If `days_overdue <= 0`, the invoice is not-yet-due and is excluded from scoring as per §3).*

### 4.2 Component B: Outstanding Amount (Weight: Up to 25 Points — USD Only)
Evaluated on `outstanding_amount` (not total amount). Amount thresholds apply to USD only. If `currency != "USD"`, 0 points are assigned and `"amount_scoring_unavailable_for_currency"` is added to `unavailable_information`.

| Condition (USD) | Points | Factor Name | Factor Description |
| :--- | :---: | :--- | :--- |
| $\text{outstanding} < \$500.00$ | 5 | `amount_low` | Balance is under $500. Lower balance risk. |
| $\$500.00 \le \text{outstanding} < \$2,000.00$ | 12 | `amount_medium` | Moderate exposure ($500 to $1,999.99). |
| $\$2,000.00 \le \text{outstanding} < \$5,000.00$ | 18 | `amount_high` | Substantial balance ($2,000 to $4,999.99). |
| $\text{outstanding} \ge \$5,000.00$ | 25 | `amount_critical` | High capital exposure ($\ge \$5,000.00). High financial impact. |

### 4.3 Component C: Reminder History & Unsuccessful Follow-ups (Weight: Up to 20 Points)
Counts only reminders verified as delivered in the audit log (never drafts or copied text).

| Condition | Points | Factor Name | Factor Description |
| :--- | :---: | :--- | :--- |
| `reminder_count == 0` | 0 | `no_reminders` | No verified follow-ups dispatched yet. |
| `reminder_count == 1` | 6 | `single_unanswered_reminder` | 1 verified reminder delivered with no payment. |
| `reminder_count == 2` | 12 | `multiple_unanswered_reminders` | 2 verified reminders delivered with no payment. |
| `reminder_count >= 3` | 20 | `repeated_unsuccessful_reminders` | 3+ verified reminders delivered. Contact fatigue / non-response. |

### 4.4 Component D: Customer History & Risk Signals (Weight: Up to 15 Points)
Combines verified customer history and promise-to-pay status. Total points in Component D are clamped to a maximum of 15 points.

| Condition | Points | Factor Name | Factor Description |
| :--- | :---: | :--- | :--- |
| `payment_history == "late"` | 15 | `customer_history_late` | Documented history of repeated late payments. |
| `payment_history == "mixed"` | 8 | `customer_history_mixed` | Mixed history of on-time and late payments. |
| `payment_history == "on_time"` | 0 | `customer_history_good` | Consistent on-time payment track record. |
| `payment_history is None` (Missing) | 5 | `customer_history_unavailable` | Customer payment history unavailable. Baseline neutral factor (5 pts) applied. Marked `is_assumption: true`. |
| Broken Promise (`has_promise_to_pay=True` and `promise_due_date < today` and unpaid) | 10 | `broken_promise` | Debtor missed promised payment date of {promise_due_date}. |

*Component D Total:* $\min(15, \sum \text{Points}_{\text{Component D}})$.

---

## 5. Handling Missing Data & Assumptions

- If `payment_history` is missing or unverified, it is recorded in `unavailable_information`: `["customer_payment_history"]`.
- The factor carries `is_assumption: true` in the output structure:
  ```json
  {
    "factor_name": "customer_history_unavailable",
    "points": 5,
    "description": "Customer payment history unavailable. Baseline neutral factor (5 pts) applied as an assumption.",
    "is_assumption": true
  }
  ```
- If currency is not USD: `["amount_scoring_unavailable_for_currency"]` is added to `unavailable_information`.

---

## 6. Priority Classification Bands

| Score Range | Priority Band | Recommended Action Urgency |
| :--- | :--- | :--- |
| **75 – 100** | `CRITICAL` | Immediate intervention required; high balance or severe aging. |
| **50 – 74** | `HIGH` | Active recovery needed; significant aging or repeated unanswered follow-ups. |
| **25 – 49** | `MEDIUM` | Standard follow-up required; moderately overdue with moderate exposure. |
| **0 – 24** | `LOW` | Gentle reminder or newly overdue invoice; healthy history. |

---

## 7. Next-Best-Action Decision Rules (Evaluated with `today`)

The action recommendation order is evaluated strictly as follows:

```text
1. Excluded Statuses:
   IF status in [PAID, CANCELLED] -> Action = "no_action_required" ("Invoice is settled or cancelled.")
   IF status == "DISPUTED" -> Action = "manual_review" ("Invoice is in active dispute. Automated outreach paused.")
   IF status == "DRAFT" -> Action = "send_invoice" ("Invoice is in draft mode and has not yet been issued.")
   IF status not in recognized -> Action = "manual_review" ("Unrecognized invoice status.")

2. Not-Yet-Due:
   IF days_overdue <= 0 -> Action = "wait" ("Invoice is not yet due.")

3. Escalations (Manual Review overrides cooldown):
   IF reminder_count >= 3 OR days_overdue > 45 ->
      Action = "manual_review"
      Reason = "Repeated follow-ups ({reminder_count}) or severe delinquency ({days_overdue} days) require human account review."

4. Broken Promise to Pay:
   IF has_promise_to_pay == True AND promise_due_date < today ->
      Action = "send_firm_followup"
      Reason = "Customer committed to pay by {promise_due_date} but balance remains unpaid. Immediate firm follow-up required."

5. Active Promise to Pay:
   IF has_promise_to_pay == True AND promise_due_date >= today ->
      Action = "schedule_later_followup"
      Reason = "Customer committed to pay on {promise_due_date}. Follow up on the agreed commitment date."

6. Reminder Cooldown Guard:
   IF last_reminder_date is not None AND (today - last_reminder_date).days < REMINDER_COOLDOWN_DAYS (3 days) ->
      Action = "wait_for_response"
      Reason = "Reminder delivered on {last_reminder_date}. Cooldown period active ({days_since} of 3 days elapsed). Wait for customer response before follow-up."

7. Overdue Tone Progression:
   IF days_overdue > 14 OR reminder_count == 2 ->
      Action = "send_firm_followup"
      Reason = "Invoice is significantly overdue (15–45 days) or 2 prior reminders were delivered without payment. Firm follow-up required."

   ELSE ->
      Action = "send_polite_reminder"
      Reason = "Invoice is newly overdue (1–14 days) with 0–1 prior follow-ups. A polite reminder preserves customer relationship while prompting settlement."
```

---

## 8. Strategy Matrix & Endpoint

The `/api/recovery/invoices/{id}/strategies` endpoint returns all four possible strategies, each classified as `recommended`, `applicable`, or `not_recommended` with a tailored explanation based on invoice facts:

1. **Polite Reminder:**
   - *Status:* `recommended` when 1–14 days overdue and 0–1 prior reminders.
   - *Advantages:* Preserves relationship; non-adversarial; low friction.
   - *Limitations:* Ineffective against habitual late payers; low urgency.
2. **Firm Follow-up:**
   - *Status:* `recommended` when 15–45 days overdue, 2 prior reminders, or broken payment promise.
   - *Advantages:* Clearly communicates outstanding balance and urgency; prompts direct resolution.
   - *Limitations:* More assertive tone may cause friction with sensitive relationships.
3. **Scheduled Later Follow-up:**
   - *Status:* `recommended` when an active, future-dated payment promise exists.
   - *Advantages:* Respects customer commitment; avoids repetitive contact.
   - *Limitations:* Delays active collection; relies on debtor honoring commitment.
4. **Manual Review Escalation:**
   - *Status:* `recommended` when >45 days overdue, 3+ prior reminders, disputes, or unrecognized status.
   - *Advantages:* Enables personalized human negotiation, account terms review, or settlement discussions.
   - *Limitations:* Requires merchant staff time; cannot be automated.

---

## 9. Configuration & Versioning (`backend/recovery/config.py`)

All weights, thresholds, cooldowns, and version metadata are isolated in `backend/recovery/config.py`:
- `SCORING_VERSION = "1.0.0"`
- `REMINDER_COOLDOWN_DAYS = 3`
- Priority score boundaries: `[25, 50, 75]`
- Days overdue boundaries: `[1, 7, 8, 14, 15, 30, 45]`
- Amount boundaries (USD): `[500.00, 2000.00, 5000.00]`

`SCORING_VERSION` is stamped onto every score response and audit log entry.

---

## 10. Limitations

1. **Fixed Dollar Thresholds:** Amount tiers ($500, $2,000, $5,000) are default thresholds designed for small-to-medium business invoices and may require custom calibration for enterprise transactions.
2. **Decision-Support Scope:** The score is a prioritization aid reflecting operational risk, not an empirical payment probability or recovery guarantee.
3. **Data Dependency:** Accuracy of scoring depends strictly on verified invoice states, delivery audit logs, and verified payment promises recorded in the backend.
