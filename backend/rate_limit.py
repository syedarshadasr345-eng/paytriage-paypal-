"""
PayTriage — In-Memory Rate Limiter Middleware / Dependency
Strictly conforms to phase6.md: Rate limiting on AI, assistant, action, and login endpoints.
Thread-safe in-memory sliding window rate limiter.
"""

import time
from collections import defaultdict
from threading import Lock

from fastapi import HTTPException, Request

_lock = Lock()
_request_records: dict[str, list[float]] = defaultdict(list)

# Limits per endpoint category: (max_requests, window_seconds)
RATE_LIMITS = {
    "login": (10, 60),      # 10 login attempts per minute
    "ai": (30, 60),         # 30 AI explain/reminder requests per minute
    "assistant": (30, 60),  # 30 assistant messages per minute
    "actions": (40, 60),    # 40 action proposals/approvals/execs per minute
}


def check_rate_limit(category: str, client_id: str) -> None:
    """Enforce sliding-window rate limit for a client identifier and category."""
    if category not in RATE_LIMITS:
        return

    max_reqs, window = RATE_LIMITS[category]
    now = time.time()
    cutoff = now - window
    key = f"{category}:{client_id}"

    with _lock:
        # Prune older timestamps
        timestamps = [t for t in _request_records[key] if t > cutoff]
        if len(timestamps) >= max_reqs:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded for {category}. Maximum {max_reqs} requests per {window}s.",
                headers={"Retry-After": str(int(window))},
            )
        timestamps.append(now)
        _request_records[key] = timestamps


def rate_limiter(category: str):
    """FastAPI dependency for rate limiting."""
    def dependency(request: Request):
        # Extract IP or token for identification
        client_ip = request.client.host if request.client else "127.0.0.1"
        auth_header = request.headers.get("authorization", "")
        identifier = f"{client_ip}:{auth_header[:20]}"
        check_rate_limit(category, identifier)
    return dependency


def reset_rate_limits() -> None:
    """Utility for unit tests to reset in-memory rate limit records."""
    with _lock:
        _request_records.clear()

