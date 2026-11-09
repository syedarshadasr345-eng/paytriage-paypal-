"""
PayTriage AI Package — AI Explanations, Reminder Drafting & Recovery Assistant
Strictly conforms to phase3.md and RULES.md (§4, §6).
"""

from backend.ai.config import GEMINI_MODEL, get_gemini_api_key, is_gemini_available
from backend.ai.router import router as ai_router

__all__ = ["GEMINI_MODEL", "ai_router", "get_gemini_api_key", "is_gemini_available"]
