# PHASE 1 — Repository Audit (READ-ONLY)

> First read `RULES.md` fully. Its rules apply to this phase.
> **Do not modify, create, or delete any project file in this phase.**

## Goal
Understand exactly what exists today so later phases improve it instead of rebuilding it.

## Tasks
1. Inspect the entire frontend and backend structure (print a folder tree).
2. Identify the languages, frameworks, libraries, database, and package managers in use.
3. List every existing API endpoint: method, path, purpose, request/response shape.
4. Check whether the frontend actually calls the backend, or uses hardcoded/mock data.
5. Check whether AI functionality is genuinely implemented or only simulated. Name the file and line.
6. Check whether PayPal Sandbox integration actually works or is decorative.
7. Find incomplete features, bugs, security weaknesses (exposed secrets, open CORS, missing validation, missing auth), and duplicate code.
8. Identify which existing features should be preserved.
9. Try to run the app (install, start backend, start frontend). Report the exact commands and any errors, unedited.

## Evidence rule
For every claim, cite the file path (and function/line where possible). If you could not verify something, write "Not verified" instead of guessing.

## Deliverable: Audit Report
Use exactly these sections:

1. **Tech stack summary**
2. **Project structure**
3. **API endpoint table**
4. **Already working** (verified by running or reading code)
5. **Partially working**
6. **Not implemented**
7. **Needs fixing** (bugs, security issues, duplicates, ranked by severity)
8. **Mock/hardcoded data found** (list each location)
9. **Recommended implementation order** (mapped to Phases 2–7)
10. **Questions for me** (missing credentials, unclear requirements)

## Stop
End with: "Phase 1 complete. Awaiting your approval before Phase 2."
Do not start Phase 2.
