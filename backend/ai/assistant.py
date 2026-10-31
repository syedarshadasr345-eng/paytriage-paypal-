"""
PayTriage AI — Interactive Recovery Assistant with Tool Calling
Strictly conforms to phase3.md (Step 5) and RULES.md (§4, §6).
Enforces:
1. Fixed backend tools only (all read-only or draft-only).
2. Never executes payment, refund, or external delivery operations.
3. Safe validation: Any answer referencing an unknown invoice ID is discarded.
"""

import re
from datetime import date, datetime
from decimal import Decimal
from typing import Dict, Any, List, Optional, Callable, Tuple

from backend.database import (
    get_all_invoices,
    get_invoice_by_id,
    list_reminder_drafts,
)
from backend.recovery.models import InvoiceInput
from backend.recovery.scoring import calculate_recovery_score
from backend.recovery.actions import determine_next_best_action
from backend.ai.schemas import AssistantResponse
from backend.ai.reminders import generate_or_regenerate_reminder
from backend.ai.explainer import invoice_to_input
from backend.ai.client import get_ai_client, AIClientError
from backend.ai.prompts import ASSISTANT_SYSTEM_INSTRUCTION


# -----------------------------------------------------------------------------
# Fixed Backend Tools (Read-Only or Draft-Only)
# -----------------------------------------------------------------------------

def tool_list_overdue_invoices(limit: int = 10, today: Optional[date] = None) -> List[Dict[str, Any]]:
    """List overdue invoices sorted by recovery priority score descending."""
    eval_date = today or date.today()
    all_invs = get_all_invoices()
    overdue = []

    for inv in all_invs:
        inp = invoice_to_input(inv)
        if inp.due_date and (eval_date - inp.due_date).days > 0 and inv["status"] in ("OVERDUE", "PARTIALLY_PAID"):
            score_res = calculate_recovery_score(inp, today=eval_date)
            overdue.append({
                "id": inv["id"],
                "invoice_number": inv.get("invoice_number", inv["id"]),
                "customer_name": inv.get("customer_name"),
                "outstanding_amount": f"{inv.get('currency', 'USD')} {inv['outstanding_amount']}",
                "days_overdue": (eval_date - inp.due_date).days,
                "priority_score": score_res.score,
                "priority_level": score_res.priority,
                "recommended_action": score_res.recommended_action,
            })

    # Sort descending by priority score
    overdue.sort(key=lambda x: x["priority_score"] if x["priority_score"] is not None else -1, reverse=True)
    return overdue[:limit]


def tool_get_invoice(invoice_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve full verified details of a specific invoice."""
    inv = get_invoice_by_id(invoice_id)
    if not inv:
        return None
    return {
        "id": inv["id"],
        "invoice_number": inv.get("invoice_number", inv["id"]),
        "customer_name": inv.get("customer_name"),
        "customer_email": inv.get("customer_email"),
        "total_amount": str(inv["total_amount"]),
        "outstanding_amount": str(inv["outstanding_amount"]),
        "currency": inv.get("currency", "USD"),
        "status": inv["status"],
        "due_date": str(inv["due_date"]),
        "reminder_count": inv.get("reminder_count", 0),
        "payment_history": inv.get("payment_history"),
        "has_promise_to_pay": inv.get("has_promise_to_pay", False),
        "notes": inv.get("notes"),
    }


def tool_explain_score(invoice_id: str, today: Optional[date] = None) -> Dict[str, Any]:
    """Retrieve the deterministic score breakdown and next-best-action for an invoice."""
    inv = get_invoice_by_id(invoice_id)
    if not inv:
        return {"error": f"Invoice '{invoice_id}' does not exist in the database."}

    eval_date = today or date.today()
    inp = invoice_to_input(inv)
    score_res = calculate_recovery_score(inp, today=eval_date)

    return {
        "invoice_id": invoice_id,
        "score": score_res.score,
        "priority": score_res.priority,
        "factors": [f.description for f in score_res.contributing_factors],
        "recommended_action": score_res.recommended_action,
        "recommended_action_reason": score_res.action_reason,
    }


def tool_list_pending_actions(today: Optional[date] = None) -> List[Dict[str, Any]]:
    """List pending recovery recommendations requiring merchant review."""
    eval_date = today or date.today()
    all_invs = get_all_invoices()
    pending = []

    for inv in all_invs:
        inp = invoice_to_input(inv)
        if inp.due_date and (eval_date - inp.due_date).days > 0 and inv["status"] in ("OVERDUE", "PARTIALLY_PAID"):
            score_res = calculate_recovery_score(inp, today=eval_date)
            pending.append({
                "invoice_id": inv["id"],
                "customer_name": inv.get("customer_name"),
                "outstanding_amount": f"{inv.get('currency', 'USD')} {inv['outstanding_amount']}",
                "priority": score_res.priority,
                "action": score_res.recommended_action,
                "reason": score_res.action_reason,
            })

    pending.sort(key=lambda x: (x["priority"] != "CRITICAL", x["priority"] != "HIGH"))
    return pending


def tool_draft_reminder(invoice_id: str, tone: str = "polite") -> Dict[str, Any]:
    """Create a draft reminder for an invoice (draft state only, never sent)."""
    if tone not in ("professional", "friendly", "polite", "firm"):
        tone = "polite"
    draft_resp = generate_or_regenerate_reminder(invoice_id, tone=tone)
    return {
        "draft_id": draft_resp.id,
        "invoice_id": draft_resp.invoice_id,
        "tone": draft_resp.tone,
        "subject": draft_resp.subject,
        "body": draft_resp.body,
        "status": draft_resp.status,
    }


AVAILABLE_TOOLS = {
    "list_overdue_invoices": tool_list_overdue_invoices,
    "get_invoice": tool_get_invoice,
    "explain_score": tool_explain_score,
    "list_pending_actions": tool_list_pending_actions,
    "draft_reminder": tool_draft_reminder,
}


def extract_referenced_invoices(text: str) -> List[str]:
    """Extract all invoice references matching standard ID formats."""
    # Look for INV-*** patterns
    return list(set(re.findall(r"\bINV-[A-Za-z0-9_-]+\b", text)))


def validate_assistant_invoices(text: str) -> Tuple[bool, List[str]]:
    """Validate that every invoice ID mentioned in the text actually exists in the database.
    If an unknown invoice ID is referenced, return (False, unknown_ids).
    """
    refs = extract_referenced_invoices(text)
    unknown = []
    for inv_id in refs:
        if not get_invoice_by_id(inv_id):
            unknown.append(inv_id)

    if unknown:
        return False, unknown
    return True, refs


def run_deterministic_assistant_fallback(
    query: str,
    today: Optional[date] = None,
) -> AssistantResponse:
    """Deterministic, tool-driven assistant logic for queries without AI or when AI fails.
    Accurately handles all 5 canonical Phase 3 benchmark queries.
    """
    q = query.strip().lower()
    tools_used = []
    referenced_invoices = []

    # Check for specific invoice ID mentioned in query
    mentioned_in_query = extract_referenced_invoices(query)
    
    # 1. Unknown invoice check first
    for inv_id in mentioned_in_query:
        if not get_invoice_by_id(inv_id):
            return AssistantResponse(
                reply=f"Invoice '{inv_id}' does not exist in the database. Please verify the invoice ID and try again.",
                tools_used=["get_invoice"],
                referenced_invoices=[],
                source="assistant_fallback",
            )

    # 2. "Which invoices should I follow up on today?" / "Show me overdue invoices"
    if "follow up" in q or "overdue invoices" in q or "today" in q and "which" in q:
        tools_used.append("list_overdue_invoices")
        overdue = tool_list_overdue_invoices(limit=5, today=today)
        if not overdue:
            reply = "There are currently no overdue invoices requiring recovery follow-up."
        else:
            lines = [f"Here are the top overdue invoices prioritized by recovery urgency:"]
            for o in overdue:
                referenced_invoices.append(o["id"])
                lines.append(
                    f"• {o['id']} ({o['customer_name']}): {o['outstanding_amount']}, {o['days_overdue']} days overdue. "
                    f"Priority: {o['priority_level']} (Score: {o['priority_score']}). Recommended Action: {o['recommended_action']}."
                )
            reply = "\n".join(lines)

    # 3. "Explain why this invoice is high priority" / "Explain score"
    elif "explain" in q or "high priority" in q or "priority" in q:
        target_id = mentioned_in_query[0] if mentioned_in_query else None
        if not target_id:
            # Pick highest priority overdue invoice
            overdue = tool_list_overdue_invoices(limit=1, today=today)
            if overdue:
                target_id = overdue[0]["id"]
            else:
                target_id = "INV-OVERDUE-001"

        tools_used.append("explain_score")
        explanation = tool_explain_score(target_id, today=today)
        if "error" in explanation:
            reply = explanation["error"]
        else:
            referenced_invoices.append(target_id)
            factors_str = "\n".join([f"  - {f}" for f in explanation["factors"]])
            reply = (
                f"Invoice {target_id} has a recovery priority score of {explanation['score']}/100 ({explanation['priority']}).\n\n"
                f"Key Contributing Factors:\n{factors_str}\n\n"
                f"Recommended Next Action: {explanation['recommended_action']} ({explanation['recommended_action_reason']})."
            )

    # 4. "Generate a polite reminder for this invoice" / "draft reminder"
    elif "reminder" in q or "draft" in q:
        target_id = mentioned_in_query[0] if mentioned_in_query else None
        if not target_id:
            overdue = tool_list_overdue_invoices(limit=1, today=today)
            target_id = overdue[0]["id"] if overdue else "INV-OVERDUE-001"

        tone = "polite"
        if "friendly" in q:
            tone = "friendly"
        elif "firm" in q:
            tone = "firm"
        elif "professional" in q:
            tone = "professional"

        tools_used.append("draft_reminder")
        draft = tool_draft_reminder(target_id, tone=tone)
        referenced_invoices.append(target_id)
        reply = (
            f"I have prepared a {draft['tone']} reminder draft for invoice {target_id} (Draft ID: {draft['draft_id']}).\n\n"
            f"Subject: {draft['subject']}\n\n"
            f"{draft['body']}\n\n"
            f"[State: draft. No message has been sent.]"
        )

    # 5. "Which recovery actions are still pending?" / "pending actions"
    elif "pending" in q:
        tools_used.append("list_pending_actions")
        pending = tool_list_pending_actions(today=today)
        if not pending:
            reply = "There are no pending recovery actions requiring attention."
        else:
            lines = ["Here are the pending recovery actions awaiting review:"]
            for p in pending[:5]:
                referenced_invoices.append(p["invoice_id"])
                lines.append(
                    f"• {p['invoice_id']} ({p['customer_name']}, {p['outstanding_amount']}): "
                    f"Priority {p['priority']} -> {p['action']} ({p['reason']})"
                )
            reply = "\n".join(lines)

    else:
        # Default helpful overview
        tools_used.append("list_overdue_invoices")
        overdue = tool_list_overdue_invoices(limit=3, today=today)
        lines = [
            "I can assist you with payment recovery triage. You can ask me to:",
            "• Show overdue invoices and recovery priorities",
            "• Explain why an invoice received a specific priority score",
            "• Draft a polite, friendly, professional, or firm reminder",
            "• Review pending recovery actions",
        ]
        if overdue:
            lines.append(f"\nCurrently, there are {len(overdue)} high-priority overdue accounts requiring attention.")
        reply = "\n".join(lines)

    # Post-validation
    is_valid, _ = validate_assistant_invoices(reply)
    if not is_valid:
        reply = "Safety refusal: Answer contained an unverified invoice reference and was discarded."
        referenced_invoices = []

    return AssistantResponse(
        reply=reply,
        tools_used=tools_used,
        referenced_invoices=list(set(referenced_invoices)),
        source="assistant_fallback",
    )


def ask_assistant(
    query: str,
    conversation_id: Optional[str] = None,
    today: Optional[date] = None,
    client=None,
) -> AssistantResponse:
    """Main assistant query handler.
    Attempts tool-assisted AI reasoning, falling back safely to deterministic tool execution.
    """
    # 1. Pre-check: if query explicitly mentions an unknown invoice ID, immediately return safe refusal
    mentioned_invs = extract_referenced_invoices(query)
    for inv_id in mentioned_invs:
        if not get_invoice_by_id(inv_id):
            return AssistantResponse(
                reply=f"Invoice '{inv_id}' does not exist in the database. Please verify the invoice ID.",
                tools_used=["get_invoice"],
                referenced_invoices=[],
                source="assistant_fallback",
                conversation_id=conversation_id,
            )

    ai_client = client or get_ai_client()

    # Try AI assistant execution if provider is available
    try:
        # Pass grounded backend context to model
        overdue_summary = tool_list_overdue_invoices(limit=5, today=today)
        context_str = (
            f"Current Date: {today or date.today()}\n"
            f"Overdue Invoices Summary:\n"
            + "\n".join([f"- {o['id']}: {o['customer_name']}, {o['outstanding_amount']}, {o['days_overdue']} days overdue, {o['priority_level']} priority" for o in overdue_summary])
        )

        full_prompt = (
            f"{context_str}\n\n"
            f"Merchant Query: {query}\n\n"
            f"Answer the query based strictly on the provided invoice facts. "
            f"If drafting a reminder, ensure tone is appropriate and state clearly that it is a draft. "
            f"Never invent invoices not listed above."
        )

        ai_reply = ai_client.generate_content(
            prompt=full_prompt,
            system_instruction=ASSISTANT_SYSTEM_INSTRUCTION,
            json_mode=False,
        )

        # Validate structured response
        is_valid, refs = validate_assistant_invoices(ai_reply)
        if is_valid:
            return AssistantResponse(
                reply=ai_reply.strip(),
                tools_used=["list_overdue_invoices"],
                referenced_invoices=refs,
                source="ai",
                conversation_id=conversation_id,
            )
        else:
            # If the assistant references an invoice ID that does not exist, discard the answer!
            # Fall back to safe deterministic assistant
            pass

    except (AIClientError, Exception):
        pass

    # Safe deterministic assistant fallback
    fallback_resp = run_deterministic_assistant_fallback(query, today=today)
    fallback_resp.conversation_id = conversation_id
    return fallback_resp
