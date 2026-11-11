# PayTriage Architecture

PayTriage is an intelligent, explainable payment recovery decision-support system for merchants managing overdue accounts with PayPal Invoicing integration.

```mermaid
flowchart TD
    UI["React 19 + TypeScript Frontend\n(In-memory auth, 8 views)"]
    API["FastAPI REST Backend\n(Pydantic validation, CORS, Rate Limit)"]
    DB[("SQLite Database\n(Invoices, Approvals, Activity Logs)")]
    Engine["Deterministic Scoring Engine\n(40/25/20/15 weights, 0-100 score)"]
    AI["Grounded AI Service\n(Gemini 3.8 Flash + Template Fallback)"]
    PP["PayPal Invoicing v2 API\n(OAuth caching, Sync, Remind, Send)"]
    Gate["Human Approval Gate\n(SHA-256 integrity, Non-repudiation)"]

    UI -->|REST + Bearer Token| API
    API --> Engine
    API --> AI
    API --> Gate
    Gate -->|Verified Execution| PP
    Gate -->|Audit Records| DB
    Engine --> DB
```

## System Components

1. **Frontend (`frontend/`)**: React 19, TypeScript, Vite. Operates with in-memory session tokens (strictly avoiding `localStorage`). Priority indicators use semantic colors (Critical red, High orange, Medium amber, Low green).
2. **Backend API (`backend/`)**: FastAPI with async lifespan, Pydantic v2 schemas for all payloads, and strict CORS.
3. **Scoring Engine (`backend/recovery/`)**: Pure deterministic function evaluating Days Overdue (up to 40), Amount (up to 25), Reminder History (up to 20), and Risk/History Signals (up to 15). Priority bands: Critical (75-100), High (50-74), Medium (25-49), Low (0-24).
4. **AI Grounded Explainer & Assistant (`backend/ai/`)**: Integrates `gemini-3.8-flash` with strict JSON schemas, XML boundary delimiters against prompt injection, and deterministic rule-based template fallback upon timeout or quota limits.
5. **PayPal Invoicing v2 Service (`backend/paypal/`)**: OAuth client credentials token manager with thread-safe caching and expiry buffer. Supports invoice synchronization, status mapping, live transmission, and verification.
6. **Human Approval Gate (`backend/actions/`)**: Pre-action proposal generating SHA-256 payload digest. Enforces merchant human approval (AI agents cannot approve or execute) and rejects modified parameters with HTTP 409 Conflict.
