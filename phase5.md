# PHASE 5 — Approval Flow, Frontend, and User Experience

> First read `RULES.md` (especially §7 and §10). Phase 4 must be approved.

## Goal
Build the backend approval gate first, then the polished fintech UI around it.

## Part A — Backend approval gate (do this first)
- Table or model: `approvals` with `id`, `invoice_id`, `action_type`, `parameters`, `hash`, `status`, `created_by`, `created_at`, `expires_at`, `used_at`.
- `POST /api/actions/propose` stores the exact action and parameters (for example the final edited reminder text), computes a hash, and returns `approval_id`.
- `POST /api/actions/{approval_id}/approve` is performed by the authenticated user only.
- `POST /api/actions/{approval_id}/execute`:
  - Recompute the hash from the submitted action. If it differs → reject, and require re-approval.
  - Reject if expired, already used, or not approved.
  - Mark as used atomically so duplicates cannot run twice.
  - Execute only supported operations (Phase 4 PayPal functions or recording a copied draft).
  - After execution, verify the result (re-fetch from PayPal) before marking `verified`.
- Statuses: `draft → copied → approved → executed → verified` (plus `failed`, `expired`, `rejected`).
- Audit log entry for every transition, with user, time, and result.
- AI and assistant can propose but can never approve or execute.

## Part B — Frontend (inspect the existing UI first; improve, don't rewrite)

**Command Center (dashboard)**
Total invoices, paid, unpaid, overdue, total outstanding, high-priority count, recovery activity, recent updates. All numbers from the API.

**Recovery Center**
Prioritized queue with score, priority level, days overdue, recommended action, reason, and action status. Filters (priority, status, overdue range) and sorting.

**Invoice detail**
Score breakdown with contributing factors, AI explanation panel (labelled when the fallback was used), strategy comparison, and unavailable-data notices.

**Reminder editor and approval**
Tone selector, Generate, Regenerate, Edit, Copy, Approve. A confirmation dialog shows the exact action and parameters being approved. Editing after approval invalidates the approval and the UI says so.

**Activity log**
Chronological, real entries, with distinct status labels. "Sent/Delivered" appears only for verified results.

**Assistant panel**
Chat connected to the backend assistant. Suggestions for example prompts.

## UX rules
- Clean, professional fintech look. Strong hierarchy, consistent spacing, readable typography, accessible contrast.
- Responsive at desktop, tablet, and mobile widths. Check all three.
- Subtle animation only. No excessive gradients or glassmorphism.
- Loading, empty, error, success, and confirmation states on every data view.
- Every button works or is clearly disabled with an explanation. No fake buttons.
- PayPal not configured → visible setup state.

## Tests
- Frontend-to-backend integration: each screen loads real API data.
- Approval flow end to end.
- Changed action after approval → blocked.
- Duplicate execute → blocked.
- Expired approval → blocked.
- Error states render when the API fails.

Provide the exact commands to run the app and tests. Describe what you verified visually and what you could not.

## End-of-phase report (required)
1. What was implemented
2. Files changed
3. What works
4. Tests performed and actual results (pasted output)
5. Remaining issues
6. What needs my approval next

End with: "Phase 5 complete. Awaiting your approval before Phase 6."
