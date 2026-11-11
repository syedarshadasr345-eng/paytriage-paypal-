"""
PayTriage Auth — Authentication Router
Endpoints for merchant login, session verification, and profile.
"""

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from backend.auth.config import (
    DEFAULT_MERCHANT_ID,
    create_session_token,
    get_demo_user,
    get_missing_auth_config,
    verify_password,
    verify_session_token,
)
from backend.auth.service import get_current_user
from backend.rate_limit import rate_limiter

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str = Field(..., description="Merchant username or email")
    password: str = Field(..., description="Merchant password")


class UserProfile(BaseModel):
    email: str
    merchant_id: str
    role: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserProfile


@router.post("/login", response_model=LoginResponse, dependencies=[Depends(rate_limiter("login"))])
def login(req: LoginRequest):
    """Authenticate merchant and issue signed session token."""
    missing = get_missing_auth_config()
    if missing:
        raise HTTPException(
            status_code=500,
            detail=f"Authentication configuration missing or placeholder: {', '.join(missing)}",
        )

    demo_user = get_demo_user()
    username_clean = req.username.strip().lower()
    demo_clean = (demo_user or "").strip().lower()

    if not demo_user or username_clean != demo_clean or not verify_password(req.password):
        raise HTTPException(
            status_code=401,
            detail="Invalid credentials. Please verify your merchant username and password.",
        )

    token = create_session_token(
        user_email=demo_user,
        merchant_id=DEFAULT_MERCHANT_ID,
        role="merchant",
        expires_in_hours=24,
    )

    return LoginResponse(
        access_token=token,
        token_type="bearer",
        user=UserProfile(
            email=demo_user,
            merchant_id=DEFAULT_MERCHANT_ID,
            role="merchant",
        ),
    )


@router.get("/me", response_model=UserProfile)
def get_profile(user: dict[str, Any] = Depends(get_current_user)):
    """Retrieve profile of currently authenticated merchant session."""
    return UserProfile(
        email=user["sub"],
        merchant_id=user["merchant_id"],
        role=user["role"],
    )


@router.get("/status")
def get_auth_status(authorization: str | None = Header(None)):
    """Safe session verification endpoint for frontend state initialization."""
    if not authorization:
        return {"authenticated": False, "user": None}
    try:
        parts = authorization.split(" ", 1)
        if len(parts) == 2 and parts[0].lower() == "bearer":
            payload = verify_session_token(parts[1].strip())
            if payload:
                return {
                    "authenticated": True,
                    "user": {
                        "email": payload["sub"],
                        "merchant_id": payload["merchant_id"],
                        "role": payload["role"],
                    },
                }
    except Exception:
        pass
    return {"authenticated": False, "user": None}

