# PHASE 4 — PayPal Sandbox Integration

> First read `RULES.md` (especially §8). Phase 3 must be approved.
> **Sandbox credentials only.** Never use live credentials.

## Goal
Implement genuine PayPal Sandbox functionality, verified step by step. No simulated successes.

## Before coding
1. Read the **current** official PayPal documentation for the Invoicing API and OAuth at developer.paypal.com. Do not rely on memory for endpoints, fields, or status values.
2. If you cannot access the docs, stop and ask me to paste the relevant sections.
3. Confirm with me that `PAYPAL_CLIENT_ID` and `PAYPAL_CLIENT_SECRET` (Sandbox) are in `.env`. Add placeholders to `.env.example`. Confirm `.env` is in `.gitignore`.

## Build in this exact order. Verify each step before the next.

**Step 1 — Authentication**
- Backend-only OAuth token retrieval with caching and expiry handling.
- Run a standalone test script. Report the real result (success or exact error).

**Step 2 — Create an invoice in Sandbox**
- Create one invoice through the API. Confirm it appears in the Sandbox dashboard and report the invoice ID.

**Step 3 — Retrieve invoice status**
- Fetch the invoice and map PayPal statuses to the app's statuses. Document the mapping.
- Validate the response with Pydantic. Unknown or unexpected fields must not crash the app.

**Step 4 — Synchronize**
- Sync PayPal invoice data into the app's own data in a way that fits the existing design.
- Never mark an invoice paid without PayPal evidence in the response.

**Step 5 — Supported invoice operation**
- Implement only operations the PayPal API supports (for example send or remind), confirmed in the docs.
- Record the real result returned by PayPal. Do not assume success.

**Step 6 — Payment verification**
- After an operation, re-fetch the invoice and record the verified state.

## Safety requirements
- Use idempotency (such as request IDs) where PayPal supports it, plus a local duplicate guard.
- Handle: invalid credentials, expired token, network failure, timeout, rate limit, 4xx/5xx errors, malformed responses.
- Safe error messages to the client. Full details only in server logs, without secrets.
- If credentials are missing, the app shows a clearly labelled "PayPal Sandbox not configured" setup state. It must not pretend to be connected.
- **PayPal operations must not be reachable from the UI or from the AI yet.** Expose them only as service functions plus test scripts. The approval gate in Phase 5 will control access.

## Tests
- Auth success and failure
- Create, fetch, and status mapping
- Missing credentials → setup state
- API failure → safe error
- Duplicate request → no duplicate operation
- Malformed response → handled
- Mock-based tests for unit coverage, plus real Sandbox tests when credentials exist (mark them clearly as live)

## End-of-phase report (required)
1. What was implemented
2. Files changed
3. What works (state which steps were verified live against Sandbox and which only with mocks)
4. Tests performed and actual results (pasted output)
5. Remaining issues
6. What needs my approval next

End with: "Phase 4 complete. Awaiting your approval before Phase 5."
