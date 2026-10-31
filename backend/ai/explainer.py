"""
PayTriage AI — Grounded Recovery Explanation Engine
Strictly conforms to phase3.md (Step 2 & Step 3) and RULES.md (§4, §6).
Pattern: Backend computes facts -> AI explains -> Output validated -> Fallback if it fails.
"""

import re
from datetime import date, datetime
from decimal import Decimal
from typing import Dict, Any, List, Optional

from backend.database import get_invoice_by_id, log_activity
from backend.recovery.models import InvoiceInput
from backend.recovery.scoring import calculate_recovery_score
from backend.recovery.actions import determine_next_best_action
from backend.ai.schemas import ExplanationResponse
from backend.ai.prompts import EXPLAINER_SYSTEM_INSTRUCTION, build_explainer_prompt
from backend.ai.client import get_ai_client, AIClientError, AISchemaValidationError
from backend.ai.config import is_gemini_available


def invoice_to_input(inv: Dict[str, Any]) -> InvoiceInput:
    """Map DB dictionary to recovery engine InvoiceInput model."""
    due = inv["due_date"]
    if isinstance(due, str):
        due = date.fromisoformat(due)
    last_rem = inv.get("last_reminder_date")
    if isinstance(last_rem, str):
        last_rem = date.fromisoformat(last_rem)
    promise_due = inv.get("promise_due_date")
    if isinstance(promise_due, str):
        promise_due = date.fromisoformat(promise_due)

    return InvoiceInput(
        invoice_id=inv["id"],
        total_amount=Decimal(str(inv["total_amount"])),
        outstanding_amount=Decimal(str(inv["outstanding_amount"])),
        currency=inv.get("currency", "USD"),
        status=inv["status"],
        due_date=due,
        reminder_count=int(inv.get("reminder_count", 0)),
        last_reminder_date=last_rem,
        payment_history=inv.get("payment_history"),
        has_promise_to_pay=bool(inv.get("has_promise_to_pay", False)),
        promise_due_date=promise_due,
    )


def compile_verified_facts(inv: Dict[str, Any], today: Optional[date] = None) -> Dict[str, Any]:
    """Assemble deterministic, verified facts from backend records and scoring engine."""
    eval_date = today or date.today()
    inp = invoice_to_input(inv)
    score_res = calculate_recovery_score(inp, today=eval_date)

    days_overdue = (eval_date - inp.due_date).days if inp.due_date else 0

    unavailable = []
    if not inv.get("payment_history"):
        unavailable.append("Customer historical payment reliability data is not on record.")
    if not inv.get("customer_email"):
        unavailable.append("Customer primary contact email is not on file.")
    if not inv.get("notes") or not str(inv.get("notes")).strip():
        unavailable.append("No prior account notes or merchant comments recorded.")
    if not inv.get("last_reminder_date") and int(inv.get("reminder_count", 0)) > 0:
        unavailable.append("Exact date of previous reminder transmission is missing from legacy record.")

    return {
        "id": inv["id"],
        "invoice_number": inv.get("invoice_number", inv["id"]),
        "customer_name": inv.get("customer_name", "Customer"),
        "customer_email": inv.get("customer_email"),
        "currency": inv.get("currency", "USD"),
        "total_amount": inv["total_amount"],
        "outstanding_amount": inv["outstanding_amount"],
        "status": inv["status"],
        "due_date": inp.due_date,
        "days_overdue": max(0, days_overdue),
        "notes": inv.get("notes"),
        "payment_history": inv.get("payment_history"),
        "reminder_count": int(inv.get("reminder_count", 0)),
        "last_reminder_date": inp.last_reminder_date,
        "has_promise_to_pay": inp.has_promise_to_pay,
        "promise_due_date": inp.promise_due_date,
        "priority_score": score_res.score,
        "priority_level": score_res.priority,
        "score_factors": [f.description for f in score_res.contributing_factors],
        "recommended_action": score_res.recommended_action,
        "recommended_action_reason": score_res.action_reason,
        "unavailable_fields": unavailable,
        "scoring_version": score_res.scoring_version,
    }


def generate_template_fallback_explanation(facts: Dict[str, Any]) -> ExplanationResponse:
    """Deterministic, rule-based explanation when AI is unavailable or validation fails.
    Conforms strictly to phase3.md Step 2: Labeled 'Generated without AI'.
    """
    days = facts["days_overdue"]
    inv_num = facts["invoice_number"]
    amt = f"{facts['currency']} {facts['outstanding_amount']}"
    score = facts["priority_score"]
    priority = facts["priority_level"]
    action_name = facts["recommended_action"]
    action_reason = facts["recommended_action_reason"]

    summary = (
        f"Invoice {inv_num} for {amt} is {days} days overdue with priority score "
        f"{score}/100 ({priority}). Deterministic evaluation indicates {action_reason}."
    )

    key_factors = list(facts["score_factors"])
    if not key_factors:
        key_factors = [
            f"Overdue by {days} days.",
            f"Outstanding balance of {amt}.",
        ]

    unavailable = list(facts["unavailable_fields"])
    if not unavailable:
        unavailable = ["All standard operational fields are populated."]

    caveats = [
        "Generated without AI — based strictly on deterministic recovery rules and database facts.",
        "Priority score is a decision-support aid, not a statistical payment probability.",
    ]

    return ExplanationResponse(
        invoice_id=facts["id"],
        summary=summary,
        key_factors=key_factors,
        recommended_action=f"{action_name}: {action_reason}",
        unavailable_information=unavailable,
        caveats=caveats,
        source="template_fallback",
        confidence_note="Generated without AI (deterministic rule-based fallback).",
        generated_at=datetime.now().isoformat(),
    )


def validate_ai_explanation(ai_data: Dict[str, Any], facts: Dict[str, Any]) -> bool:
    """Validate AI response against ground-truth facts.
    Reject and trigger fallback if:
    - Missing required fields
    - Mentions an unrecognized invoice ID (not facts['id'] or facts['invoice_number'])
    - Claims customer payment history when none was provided
    - Mentions an invented dollar amount not in facts
    """
    required_keys = ["summary", "key_factors", "recommended_action", "unavailable_information", "caveats"]
    for k in required_keys:
        if k not in ai_data or not ai_data[k]:
            return False

    full_text = f"{ai_data.get('summary', '')} {' '.join(ai_data.get('key_factors', []))} {ai_data.get('recommended_action', '')}"

    # 1. Foreign invoice ID check: Look for patterns like INV-[A-Z0-9-]+
    mentioned_invs = re.findall(r"\bINV-[A-Za-z0-9_-]+\b", full_text)
    for inv_ref in mentioned_invs:
        if inv_ref != facts["id"] and inv_ref != facts["invoice_number"]:
            return False

    # 2. Fabricated payment history check:
    # If payment_history is None/unavailable in facts, AI must NOT claim history of good/bad payments
    if facts.get("payment_history") is None:
        lowered = full_text.lower()
        forbidden_claims = [
            "good payment history",
            "reliable payment history",
            "excellent payment history",
            "history of paying on time",
            "consistent on-time payer",
            "habitual late payer",
            "consistently pays late",
        ]
        for claim in forbidden_claims:
            if claim in lowered:
                return False

    # 3. Fabricated amounts check:
    # Extract numerical monetary values mentioned (e.g., $5,000, 5000, 1200.50)
    # Check if any large dollar amount (>100) is mentioned that does not match total_amount or outstanding_amount
    valid_amounts = {
        str(facts["total_amount"]),
        str(facts["outstanding_amount"]),
        str(int(float(facts["total_amount"]))),
        str(int(float(facts["outstanding_amount"]))),
    }
    dollar_matches = re.findall(r"\$\s*([0-9]+(?:\.[0-9]{2})?)", full_text)
    for dm in dollar_matches:
        # Ignore small numbers or round thresholds (e.g. $500, $2000, $5000 tiers)
        if dm not in valid_amounts and dm not in ["500", "2000", "5000", "500.00", "2000.00", "5000.00"]:
            return False

    return True


def explain_invoice_recovery(
    invoice_id: str,
    today: Optional[date] = None,
    client=None,
) -> ExplanationResponse:
    """Generate grounded recovery explanation for an invoice.
    Always returns valid ExplanationResponse (AI-generated or template fallback).
    """
    inv = get_invoice_by_id(invoice_id)
    if not inv:
        raise ValueError(f"Invoice '{invoice_id}' not found.")

    facts = compile_verified_facts(inv, today=today)

    # Use provided client or default global client
    ai_client = client or get_ai_client()

    # Try AI generation
    try:
        prompt = build_explainer_prompt(facts)
        ai_json = ai_client.generate_json(
            prompt=prompt,
            system_instruction=EXPLAINER_SYSTEM_INSTRUCTION,
        )

        # Validate strictly against ground truth
        if validate_ai_explanation(ai_json, facts):
            # Ensure unavailable_information contains the verified missing fields
            missing_info = list(ai_json.get("unavailable_information", []))
            for item in facts["unavailable_fields"]:
                if not any(item.lower() in m.lower() for m in missing_info):
                    missing_info.append(item)

            resp = ExplanationResponse(
                invoice_id=facts["id"],
                summary=ai_json["summary"].strip(),
                key_factors=[str(f).strip() for f in ai_json.get("key_factors", [])],
                recommended_action=ai_json["recommended_action"].strip(),
                unavailable_information=missing_info,
                caveats=ai_json.get("caveats", [
                    "Advisory decision-support assessment based on verified facts.",
                    "Score does not guarantee empirical recovery outcome.",
                ]),
                source="ai",
                confidence_note="Generated with Gemini AI and grounded in verified backend facts.",
                generated_at=datetime.now().isoformat(),
            )
            log_activity(
                invoice_id=invoice_id,
                action_type="ai_explain",
                status="success",
                details="Grounded AI explanation successfully generated and validated.",
            )
            return resp

    except (AIClientError, AISchemaValidationError, Exception):
        # AI failed, timed out, or produced unvalidated data -> fallback seamlessly
        pass

    # Deterministic template fallback
    fallback_resp = generate_template_fallback_explanation(facts)
    log_activity(
        invoice_id=invoice_id,
        action_type="ai_explain",
        status="fallback",
        details="Deterministic rule-based explanation generated without AI.",
    )
    return fallback_resp
