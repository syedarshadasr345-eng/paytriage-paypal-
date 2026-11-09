"""
PayTriage Auth — Dependencies & Ownership Enforcement
Strictly conforms to phase5.md and RULES.md (§7, §9).
"""

from typing import Any

from fastapi import Depends, Header, HTTPException

from backend.auth.config import DEFAULT_MERCHANT_ID, verify_session_token


def get_current_user(authorization: str | None = Header(None)) -> dict[str, Any]:
    """FastAPI dependency to extract and authenticate current merchant session."""
    if not authorization:
        raise HTTPException(
            status_code=401,
            detail="Authentication required. Please provide Authorization Bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=401,
            detail="Invalid Authorization header format. Expected 'Bearer <token>'.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = parts[1].strip()
    payload = verify_session_token(token)
    if not payload:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired session token. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return payload


def require_merchant_user(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    """Ensure caller is a human merchant, NOT an autonomous AI agent.
    Strictly conforms to RULES.md §7: AI can propose but NEVER approve or execute.
    """
    if user.get("role") == "ai":
        raise HTTPException(
            status_code=403,
            detail="AI autonomous agents cannot approve or execute actions. Human merchant approval required.",
        )
    return user


def check_invoice_ownership(invoice: dict[str, Any], user: dict[str, Any]) -> None:
    """Enforce tenant/merchant isolation: users can only inspect and act upon their own invoices."""
    inv_merchant = invoice.get("merchant_id") or DEFAULT_MERCHANT_ID
    user_merchant = user.get("merchant_id") or DEFAULT_MERCHANT_ID

    if inv_merchant != user_merchant:
        raise HTTPException(
            status_code=403,
            detail="Forbidden: You do not have ownership access to this invoice.",
        )

