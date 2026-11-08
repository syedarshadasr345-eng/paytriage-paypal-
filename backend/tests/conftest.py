"""
PayTriage Tests — Global Pytest Configuration and Test Isolation Fixtures
Strictly conforms to phase3.md and RULES.md (§4, §6).
Guarantees the normal test suite NEVER makes network calls to Gemini API.
"""

import os
import re
import json
import pytest
from typing import Optional, Dict, Any, Type
from pydantic import BaseModel

from backend.ai.client import set_ai_client, AIClientError


class IsolatedMockGeminiClient:
    """Mock Gemini client for fast, deterministic unit test isolation without external calls."""

    def __init__(self, invoice_id: Optional[str] = None, amount: Optional[str] = None):
        self.invoice_id = invoice_id
        self.amount = amount

    def generate_json(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        response_schema: Optional[Type[BaseModel]] = None,
    ) -> Dict[str, Any]:
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
        system_instruction: Optional[str] = None,
        json_mode: bool = False,
        response_schema: Optional[Type[BaseModel]] = None,
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
