"""
PayTriage Tests — Global Pytest Configuration and Test Isolation Fixtures
Strictly conforms to phase3.md and RULES.md (§4, §6).
Guarantees the normal test suite NEVER makes network calls to Gemini API.
"""

import json
import os
import re
from typing import Any

# Set isolated test credentials for test suite when running in clean test environments
if not os.getenv("SESSION_SECRET") or os.getenv("SESSION_SECRET").startswith("your_"):
    os.environ["SESSION_SECRET"] = "test_mock_session_secret_32_characters_long_2026"
if not os.getenv("DEMO_USER") or os.getenv("DEMO_USER").startswith("your_"):
    os.environ["DEMO_USER"] = "test_merchant@example.com"
if not os.getenv("DEMO_PASSWORD") or os.getenv("DEMO_PASSWORD").startswith("your_"):
    os.environ["DEMO_PASSWORD"] = "test_mock_password_2026"

import pytest
from pydantic import BaseModel

from backend.ai.client import AIClientError, set_ai_client


class IsolatedMockGeminiClient:
    """Mock Gemini client for fast, deterministic unit test isolation without external calls."""

    def __init__(self, invoice_id: str | None = None, amount: str | None = None):
        self.invoice_id = invoice_id
        self.amount = amount

    def generate_json(
        self,
        prompt: str,
        system_instruction: str | None = None,
        response_schema: type[BaseModel] | None = None,
    ) -> dict[str, Any]:
        # Extract invoice_id and amount from prompt if present
        inv_match = re.search(r'"invoice_id":\s*"([^"]+)"', prompt)
        inv_id = inv_match.group(1) if inv_match else (self.invoice_id or "INV-SEV-009")

        amt_match = re.search(r'"outstanding_amount":\s*"([^"]+)"', prompt)
        amt = amt_match.group(1) if amt_match else (self.amount or "7500.00")

        # Reminder generator check
        if system_instruction and "reminder" in system_instruction.lower():
            due_match = re.search(r'"due_date":\s*"([^"]+)"', prompt)
            due = due_match.group(1) if due_match else "2026-11-01"
            return {
                "subject": f"Notice regarding Invoice {inv_id}",
                "body": f"Please note Invoice {inv_id} for USD {amt} was due on {due}. Please remit payment.",
            }

        # Explanation generator check
        return {
            "summary": f"Invoice {inv_id} has an outstanding balance of USD {amt} and requires priority collection.",
            "key_factors": [
                "Overdue by 35 days (maximum aging tier)",
                f"Significant outstanding balance of USD {amt}",
            ],
            "recommended_action": "manual_review: High-value account overdue > 30 days requires direct human escalation.",
            "unavailable_information": ["Customer historical payment reliability data is not on record."],
            "caveats": ["Decision-support assessment based on verified facts."],
        }

    def generate_content(
        self,
        prompt: str,
        system_instruction: str | None = None,
        json_mode: bool = False,
        response_schema: type[BaseModel] | None = None,
    ) -> str:
        if json_mode:
            return json.dumps(self.generate_json(prompt, system_instruction, response_schema))
        raise AIClientError("Isolated unit test environment: AI generation disabled.")


@pytest.fixture(autouse=True)
def isolate_ai_environment(request, monkeypatch):
    """Ensure normal test suite NEVER calls real Gemini API.
    Clears GEMINI_API_KEY and GOOGLE_API_KEY and sets mock AI client
    for all non-live tests.
    Live tests must be marked with @pytest.mark.live_ai and require RUN_LIVE_AI=1.
    """
    is_live = request.node.get_closest_marker("live_ai") is not None

    if is_live:
        if os.getenv("RUN_LIVE_AI", "").strip() != "1":
            pytest.skip("Live AI test skipped by default. Set RUN_LIVE_AI=1 to opt-in.")
        # Live execution allowed with real credentials
        yield
        return

    # Non-live tests: clear all real API keys
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    # Set mock client
    mock_client = IsolatedMockGeminiClient()
    set_ai_client(mock_client)
    try:
        yield mock_client
    finally:
        set_ai_client(None)


@pytest.fixture(autouse=True)
def isolate_paypal_environment(request):
    """Ensure normal test suite NEVER calls real PayPal API without opt-in.
    Live tests must be marked with @pytest.mark.live_paypal and require RUN_LIVE_PAYPAL=1.
    """
    is_live = request.node.get_closest_marker("live_paypal") is not None

    if is_live:
        if os.getenv("RUN_LIVE_PAYPAL", "").strip() != "1":
            pytest.skip("Live PayPal test skipped by default. Set RUN_LIVE_PAYPAL=1 to opt-in.")
        yield
        return

    from backend.paypal.auth import get_auth_manager
    get_auth_manager().clear_cache()
    from backend.rate_limit import reset_rate_limits
    reset_rate_limits()
    yield
    reset_rate_limits()
