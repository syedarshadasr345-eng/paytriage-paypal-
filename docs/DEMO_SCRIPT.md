# PayTriage Demo Video Script (< 3 Minutes)

## Pre-Recording Checklist
- [ ] Backend running: `uvicorn backend.main:app --port 8000`
- [ ] Frontend running: `npm run dev` in `frontend/` (port 5173)
- [ ] Browser window sized to 1080p, console open to verify zero errors
- [ ] Database seeded with benchmark records: `python backend/seed.py`
- [ ] PayPal Sandbox credentials confirmed in `backend/.env`

---

## Timed Video Script (0:00 - 2:45)

### 0:00 - 0:30 | Problem & Overview
- **Visual:** PayTriage Login screen (`http://localhost:5173`).
- **Narration:** "Merchants waste hours every week guessing which unpaid invoices to follow up on, risking cash flow and client relationships. Welcome to PayTriage: an explainable payment recovery intelligence platform built for PayPal merchants. PayTriage tells you which unpaid invoices need you first, and why."
- **Action:** Enter merchant credentials and click **Sign In to Recovery Command**.

### 0:30 - 0:55 | Command Center & Priority Queue
- **Visual:** Command Center dashboard transitioning to Recovery Center.
- **Narration:** "Immediately, the Command Center aggregates portfolio risk, highlighting total outstanding volume and high-priority accounts across both PayPal Sandbox and benchmark accounts. Navigating to the Recovery Center shows our prioritized recovery queue, ranked deterministically from 0 to 100 based on aging, balance, reminder history, and customer track record."
- **Action:** Click **Recovery Center** tab. Show filters (Critical, High, Medium, Low) and Live Sandbox vs Demo badges.

### 0:55 - 1:30 | Explainable Diagnostics & Grounded AI
- **Visual:** Invoice Detail view for live PayPal invoice `INV2-5NY5-V2PK-CASX-WNU2`.
- **Narration:** "Clicking an invoice reveals its full diagnostic breakdown. Unlike black-box models, every single point is backed by verified facts. The AI explanation panel synthesizes key factors and recommends next steps without hallucinations. If the AI provider times out or reaches quota limits, deterministic rule-based templates ensure reliable operations."
- **Action:** Point to the factor list (e.g. 20 pts moderately overdue, 12 pts balance) and the grounded explanation.

### 1:30 - 2:15 | Human Approval Gate & PayPal Verification
- **Visual:** Reminder Studio and Approval Modal.
- **Narration:** "Autonomous AI sending unauthorized messages is dangerous. In PayTriage, AI proposes reminders, but only a human merchant can approve and execute. Notice the SHA-256 cryptographic hash: if an operator edits the text after approval, the system detects parameter tampering and requires re-approval."
- **Action:** Select tone, click **Propose & Open Approval Dialog**, review hash, click **Approve Action as Merchant**, and then **Execute Approved Action Now**.

### 2:15 - 2:45 | Verified Audit Trail & Conclusion
- **Visual:** Activity Log view.
- **Narration:** "The reminder is transmitted directly through PayPal Invoicing v2 and verified against PayPal APIs. The immutable activity log labels verified transmissions strictly as 'Verified & Sent'. PayTriage brings intelligence, transparency, and safety to cash flow recovery."
- **Action:** Highlight verified record in the audit trail. Show PayPal Sandbox Connected badge.
