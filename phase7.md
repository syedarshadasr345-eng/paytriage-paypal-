# PHASE 7 — Hackathon Submission Preparation

> First read `RULES.md` (especially §13). Phase 6 must be approved.
> Document only what is actually implemented. Do not overclaim.

## Goal
Make the repository submission-ready and the demo easy to follow.

## 1. README.md
Include, in this order:
1. Product name and one-sentence value proposition
2. Problem statement
3. Solution overview
4. Key features (only the ones that work)
5. Architecture diagram (Mermaid or an image) and a short explanation
6. Technology stack
7. AI workflow (facts → AI → validation → fallback)
8. Recovery scoring methodology (weights, thresholds, exclusions; state clearly that it is a priority score, not a probability prediction)
9. Human-approval and security model
10. PayPal integration details (which APIs, which operations, what is verified)
11. Setup instructions (prerequisites, install, run backend, run frontend)
12. Environment variables (reference `.env.example`)
13. Testing instructions
14. Sandbox demonstration instructions (how to create test data and walk through the flow)
15. Known limitations (be honest)
16. Security considerations
17. License

## 2. Supporting files
- `.env.example` with placeholders only
- `LICENSE` (MIT or Apache-2.0), visible in the repository root. Ask me which one I prefer and put my name and the year in it.
- `docs/ARCHITECTURE.md` and `docs/SCORING.md` updated to the final implementation
- Optional: seed script for demo data that is clearly labelled as demo data

## 3. Demo script (video under 3 minutes)
Write `docs/DEMO_SCRIPT.md` with timestamps and narration:

- 0:00–0:30 Problem and value: the hook sentence from RULES.md §2
- 0:30–1:00 Dashboard with real data, then the Recovery Center
- 1:00–1:30 High-priority invoice, explainable score, AI explanation
- 1:30–2:15 Generate, edit, and approve the reminder; show approval protection
- 2:15–2:45 Execute the supported PayPal Sandbox operation; show the verified result and activity log
- 2:45–3:00 Close: what was built, honest limitations

Add a pre-recording checklist: clean database, Sandbox credentials working, AI key working, test invoices ready, browser zoom, no secrets visible on screen.

## 4. Final verification
- Fresh clone test: follow the README exactly on a clean setup and report every problem found.
- Run the full test suite one last time and paste the output.
- Re-run the secret scan on the repo and git history.
- Check that no feature in the README is unimplemented.
- Check that no UI text claims anything unverified (for example "Reminder Sent", "Payment Received").

## 5. Submission checklist
- [ ] Repository public (if required) with visible license
- [ ] README complete and accurate
- [ ] Demo video under 3 minutes
- [ ] Working PayPal Sandbox flow demonstrated
- [ ] AI usage clearly explained
- [ ] No secrets committed
- [ ] Tests run and results recorded
- [ ] Known limitations documented

## End-of-phase report (required)
1. What was completed
2. Files created or changed
3. Fresh-clone test results
4. Final test results (pasted output)
5. Remaining issues
6. Final submission checklist status

End with: "Phase 7 complete. Project ready for final review."
