# PHASE 6 — Security Audit and Full Testing

> First read `RULES.md` (especially §9 and §11). Phase 5 must be approved.
> Fix problems at the root cause. Do not add features in this phase.

## Part A — Security audit
Check each item, report PASS / FAIL / PARTIAL with file evidence, then fix failures:

1. No secrets in the repo or git history (search the code and `git log -p` for keys, tokens, secrets).
2. `.env` ignored; `.env.example` complete with placeholders only.
3. PayPal and AI keys never reach the frontend bundle or API responses.
4. Server-side Pydantic validation on every endpoint.
5. Authentication and authorization on all non-public endpoints.
6. Invoice ownership checks (user A cannot read or act on user B's invoice).
7. CORS restricted to known origins.
8. Rate limiting on AI, assistant, and action endpoints.
9. Approval cannot be bypassed (call execute directly, replay, tamper with parameters).
10. Duplicate operations blocked.
11. Prompt injection tests pass (invoice text cannot alter actions).
12. Error responses leak no stack traces, SQL, or secrets.
13. Money handled with Decimal or integer cents everywhere; no float math.
14. Audit log records all consequential actions and cannot be edited via the API.
15. Dependencies: run the available audit tools (`pip-audit`, `npm audit`) and report the findings.

## Part B — Full test execution
Run the entire suite and report real output. The suite must cover:

- Recovery score calculation and priority classification
- Next-best-action rules
- AI output validation
- Reminder generation
- Approval enforcement
- Invoice status handling
- PayPal Sandbox (live only if credentials are configured; otherwise state "not run")
- Frontend-to-backend integration
- Edge cases

**Required scenarios:** paid invoice, newly overdue, severely overdue, cancelled, missing customer history, failed AI provider, failed PayPal request, duplicate action request, changed action after approval.

## Part C — End-to-end run
Perform the full demo path manually or with an automated test: dashboard → Recovery Center → select invoice → score → AI explanation → generate reminder → edit → approve → execute supported operation → verified result → activity log. Report each step as pass or fail with notes.

## Rules
- Do not claim any test passed unless you executed it and can show the output.
- List every test that was skipped and why.
- Fix failures, re-run, and report the before and after.

## End-of-phase report (required)
1. Security checklist results (table)
2. Files changed
3. Test results (pasted output and a summary count)
4. Skipped or unverified items
5. Remaining issues, ranked by severity
6. What needs my approval next

End with: "Phase 6 complete. Awaiting your approval before Phase 7."
