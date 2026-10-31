"""
PayTriage AI Package — AI Explanations, Reminder Drafting & Recovery Assistant
Strictly conforms to phase3.md and RULES.md (§4, §6).
"""

from backend.ai.config import get_gemini_api_key, is_gemini_available, GEMINI_MODEL
from backend.ai.router import router as ai_router

__all__ = ["ai_router", "get_gemini_api_key", "is_gemini_available", "GEMINI_MODEL"]
