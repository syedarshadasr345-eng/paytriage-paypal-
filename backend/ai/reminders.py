"""
PayTriage AI — Grounded Payment Reminder Drafting Engine
Strictly conforms to phase3.md (Step 4) and RULES.md (§4, §6).
Enforces:
1. Strict inclusion of verified invoice reference, amount, and due date.
2. Distinct lifecycle states: draft -> copied.
3. Zero tolerance for fake 'sent' status or invented threats.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from backend.ai.client import (
    AIProviderUnavailableError,
    AISchemaValidationError,
    AITimeoutError,
    get_ai_client,
)
from backend.ai.prompts import REMINDER_SYSTEM_INSTRUCTION, build_reminder_prompt
from backend.ai.schemas import (
    ReminderCopyResponse,
    ReminderDraftResponse,
    ReminderEditRequest,
    ReminderTone,
)
from backend.database import (
    get_invoice_by_id,
    get_reminder_draft,
    log_activity,
    save_reminder_draft,
    update_reminder_draft,
)


def get_deterministic_template(facts: dict[str, Any], tone: ReminderTone) -> tuple[str, str]:
    """Generate rule-based deterministic reminder template for given tone.
    Guarantees correct invoice reference, amount, and due date.
    """
    inv_num = facts.get("invoice_number", facts["id"])
    customer = facts.get("customer_name", "Valued Customer")
    amt_str = f"{facts.get('currency', 'USD')} {facts['outstanding_amount']}"
    due_str = str(facts["due_date"])

    if tone == "friendly":
        subject = f"Friendly check-in regarding Invoice {inv_num}"
        body = (
            f"Hi {customer},\n\n"
            f"We hope you are having a wonderful week! This is a quick note to follow up on "
            f"Invoice {inv_num} for {amt_str}, which was due on {due_str}.\n\n"
            f"If you've already initiated payment, please disregard this note. If you need any assistance "
            f"or a copy of the invoice, feel free to reply directly.\n\n"
            f"Thank you for your partnership!"
        )
    elif tone == "polite":
        subject = f"Payment Reminder: Invoice {inv_num}"
        body = (
            f"Dear {customer},\n\n"
            f"This is a courteous reminder that payment for Invoice {inv_num} in the amount of "
            f"{amt_str} was due on {due_str}.\n\n"
            f"We appreciate your prompt attention to this matter. Please let us know once payment has been processed "
            f"or if you have any questions regarding the statement.\n\n"
            f"Best regards,\nAccounts Receivable Team"
        )
    elif tone == "firm":
        subject = f"Overdue Payment Notice: Invoice {inv_num}"
        body = (
            f"Dear {customer},\n\n"
            f"Our records show that Invoice {inv_num} for {amt_str} remains outstanding past its due date of {due_str}.\n\n"
            f"Please arrange payment of the outstanding balance of {amt_str} as soon as possible. "
            f"If payment has already been remitted or if you have any questions regarding this invoice, please contact our accounts department directly.\n\n"
            f"Sincerely,\nAccounts Receivable Team"
        )
    else:  # professional (default)
        subject = f"Statement of Account: Invoice {inv_num}"
        body = (
            f"Dear {customer},\n\n"
            f"Please find a reminder regarding Invoice {inv_num} for the outstanding balance of {amt_str}, "
            f"which matured on {due_str}.\n\n"
            f"Kindly confirm receipt and schedule settlement at your earliest convenience. Thank you for your business.\n\n"
            f"Regards,\nFinance Team"
        )

    return subject, body


def validate_reminder_text(subject: str, body: str, facts: dict[str, Any]) -> bool:
    """Validate that generated reminder contains required ground-truth elements:
    1. Invoice reference (invoice_number or id)
    2. Outstanding amount
    3. Due date
    4. No abusive or illegal threats (lawsuit, police, arrest, bailiff)
    """
    full_content = f"{subject} {body}"

    inv_num = facts.get("invoice_number", facts["id"])
    inv_id = facts["id"]
    if inv_num not in full_content and inv_id not in full_content:
        return False

    amt_str = str(facts["outstanding_amount"])
    # Also support integer string (e.g. 500 for 500.00)
    amt_int = str(int(Decimal(amt_str))) if "." in amt_str else amt_str
    if amt_str not in full_content and amt_int not in full_content:
        return False

    due_str = str(facts["due_date"])
    if due_str not in full_content:
        return False

    # Check for forbidden aggressive or abusive threats
    forbidden_tokens = ["lawsuit", "court order", "arrest", "police", "jail", "seize", "ruin credit"]
    lowered = full_content.lower()
    for token in forbidden_tokens:
        if token in lowered:
            return False

    return True


def generate_or_regenerate_reminder(
    invoice_id: str,
    tone: ReminderTone | None = None,
    client=None,
) -> ReminderDraftResponse:
    """Generate or regenerate a reminder draft.
    Saves the result to SQLite reminder_drafts with status 'draft'.
    Never displays 'Reminder Sent'.
    If tone is omitted, defaults based on recommended action (polite, firm, else professional).
    """
    inv = get_invoice_by_id(invoice_id)
    if not inv:
        raise ValueError(f"Invoice '{invoice_id}' not found.")

    from backend.ai.explainer import invoice_to_input
    from backend.recovery.actions import determine_next_best_action
    
    # Resolve tone: explicit override or default derived from recommended action
    if tone is not None:
        resolved_tone: ReminderTone = tone
    else:
        rec_action, _ = determine_next_best_action(invoice_to_input(inv), datetime.now().date())
        if rec_action == "send_firm_followup":
            resolved_tone = "firm"
        elif rec_action == "send_polite_reminder":
            resolved_tone = "polite"
        else:
            resolved_tone = "professional"

    facts = {
        "id": inv["id"],
        "invoice_number": inv.get("invoice_number", inv["id"]),
        "customer_name": inv.get("customer_name", "Customer"),
        "customer_email": inv.get("customer_email"),
        "currency": inv.get("currency", "USD"),
        "total_amount": inv["total_amount"],
        "outstanding_amount": inv["outstanding_amount"],
        "due_date": inv["due_date"],
        "days_overdue": max(0, (datetime.now().date() - inv["due_date"]).days) if inv.get("due_date") else 0,
        "reminder_count": int(inv.get("reminder_count", 0)),
        "notes": inv.get("notes"),
    }

    ai_client = client or get_ai_client()
    chosen_source = "ai"
    fallback_reason: str | None = None
    subject: str | None = None
    body: str | None = None

    try:
        prompt = build_reminder_prompt(facts, tone=resolved_tone)
        ai_json = ai_client.generate_json(
            prompt=prompt,
            system_instruction=REMINDER_SYSTEM_INSTRUCTION,
        )

        cand_subject = ai_json.get("subject", "").strip()
        cand_body = ai_json.get("body", "").strip()

        if validate_reminder_text(cand_subject, cand_body, facts):
            subject = cand_subject
            body = cand_body
        else:
            chosen_source = "template_fallback"
            fallback_reason = "validation_failed"
            subject, body = get_deterministic_template(facts, resolved_tone)

    except AITimeoutError:
        chosen_source = "template_fallback"
        fallback_reason = "timeout"
        subject, body = get_deterministic_template(facts, resolved_tone)
    except AIProviderUnavailableError:
        chosen_source = "template_fallback"
        fallback_reason = "provider_unavailable"
        subject, body = get_deterministic_template(facts, resolved_tone)
    except AISchemaValidationError:
        chosen_source = "template_fallback"
        fallback_reason = "schema_validation_failed"
        subject, body = get_deterministic_template(facts, resolved_tone)
    except Exception as exc:
        chosen_source = "template_fallback"
        clean_msg = str(exc).lower()
        if "timeout" in clean_msg or "timed out" in clean_msg:
            fallback_reason = "timeout"
        else:
            fallback_reason = "provider_error"
        subject, body = get_deterministic_template(facts, resolved_tone)

    draft_id = f"DRF-{uuid.uuid4().hex[:8].upper()}"
    now_iso = datetime.now().isoformat()

    draft_record = {
        "id": draft_id,
        "invoice_id": invoice_id,
        "tone": resolved_tone,
        "subject": subject,
        "body": body,
        "status": "draft",  # Strict invariant: starts in draft state
        "source": chosen_source,
        "fallback_reason": fallback_reason,
        "created_at": now_iso,
        "updated_at": now_iso,
    }

    save_reminder_draft(draft_record)

    log_activity(
        invoice_id=invoice_id,
        action_type="draft_reminder",
        status="created",
        details=f"Draft reminder generated ({tone} tone, source: {chosen_source}).",
    )

    return ReminderDraftResponse(**draft_record)


def edit_reminder_draft(draft_id: str, edit_req: ReminderEditRequest) -> ReminderDraftResponse:
    """Edit an existing reminder draft. Retains draft status."""
    existing = get_reminder_draft(draft_id)
    if not existing:
        raise ValueError(f"Reminder draft '{draft_id}' not found.")

    updates = {}
    if edit_req.subject is not None:
        updates["subject"] = edit_req.subject.strip()
    if edit_req.body is not None:
        updates["body"] = edit_req.body.strip()

    updated = update_reminder_draft(draft_id, updates)
    log_activity(
        invoice_id=existing["invoice_id"],
        action_type="edit_reminder_draft",
        status="updated",
        details=f"Draft {draft_id} updated by merchant.",
    )
    return ReminderDraftResponse(**updated)


def copy_reminder_draft(draft_id: str) -> ReminderCopyResponse:
    """Mark draft as copied when user copies text to clipboard.
    Records transition from 'draft' to 'copied'. Never 'sent'.
    """
    existing = get_reminder_draft(draft_id)
    if not existing:
        raise ValueError(f"Reminder draft '{draft_id}' not found.")

    update_reminder_draft(draft_id, {"status": "copied"})

    full_text = f"Subject: {existing['subject']}\n\n{existing['body']}"

    act_log = log_activity(
        invoice_id=existing["invoice_id"],
        action_type="copy_reminder",
        status="copied",
        details=f"Merchant copied reminder draft {draft_id} to clipboard.",
    )

    return ReminderCopyResponse(
        id=draft_id,
        invoice_id=existing["invoice_id"],
        status="copied",
        copied_text=full_text,
        activity_log_id=act_log["id"],
        message="Draft marked as copied. No email has been sent.",
    )
