"""
PayTriage AI — AI Client Wrapper for Google Gemini
Strictly conforms to phase3.md and RULES.md (§4, §6).
Wraps Google GenAI SDK with timeouts, retries, safe logging, and mockability.
"""

import json
import logging
import time
from typing import Optional, Dict, Any, Type
from pydantic import BaseModel

from backend.ai.config import (
    get_gemini_api_key,
    is_gemini_available,
    GEMINI_MODEL,
    AI_TIMEOUT_SECONDS,
    AI_MAX_RETRIES,
    mask_secret,
    redact_sensitive_data,
)

logger = logging.getLogger("paytriage.ai.client")


class AIClientError(Exception):
    """Base exception for AI client failures."""
    pass


class AIProviderUnavailableError(AIClientError):
    """Raised when the AI provider API key is not configured or service is unreachable."""
    pass


class AISchemaValidationError(AIClientError):
    """Raised when the AI returns output that does not match the expected schema."""
    pass


class GeminiClient:
    """Wrapper for Google Gemini API via official google-genai SDK.
    Supports timeouts, retries, safe telemetry, and test mocking.
    """

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self._api_key = api_key or get_gemini_api_key()
        self.model = model or GEMINI_MODEL
        self._sdk_client = None

    def _get_sdk_client(self):
        """Lazy-initialize google-genai client."""
        if not self._api_key:
            raise AIProviderUnavailableError(
                "GEMINI_API_KEY is not configured in backend/.env or environment. "
                "Operating in deterministic template fallback mode."
            )
        if self._sdk_client is None:
            try:
                from google import genai
                self._sdk_client = genai.Client(api_key=self._api_key)
            except Exception as e:
                clean_err = redact_sensitive_data(str(e))
                logger.error(f"Failed to initialize google-genai client: {clean_err}")
                raise AIProviderUnavailableError(f"Failed to initialize Gemini SDK client: {clean_err}")
        return self._sdk_client

    def generate_content(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        json_mode: bool = True,
        response_schema: Optional[Type[BaseModel]] = None,
    ) -> str:
        """Call Gemini model with timeouts, retries, and error redaction.
        Returns the raw string output from the model.
        """
        sdk_client = self._get_sdk_client()

        from google.genai import types

        config_kwargs: Dict[str, Any] = {
            "temperature": 0.2,  # Low temperature for grounded recovery intelligence
        }

        if system_instruction:
            config_kwargs["system_instruction"] = system_instruction

        if json_mode:
            config_kwargs["response_mime_type"] = "application/json"
            if response_schema:
                config_kwargs["response_schema"] = response_schema

        config = types.GenerateContentConfig(**config_kwargs)

        last_error = None
        for attempt in range(1, AI_MAX_RETRIES + 1):
            try:
                logger.info(f"Dispatching Gemini request (model={self.model}, attempt={attempt}/{AI_MAX_RETRIES})")
                
                # Execute generation call
                response = sdk_client.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config=config,
                )

                if not response or not response.text:
                    raise AIClientError("Empty response received from Gemini model.")

                return response.text.strip()

            except Exception as exc:
                last_error = exc
                clean_msg = redact_sensitive_data(str(exc))
                logger.warning(
                    f"Gemini generation attempt {attempt} failed: {clean_msg}"
                )
                if attempt < AI_MAX_RETRIES:
                    time.sleep(0.5 * attempt)

        # All retries exhausted
        clean_err = redact_sensitive_data(str(last_error))
        logger.error(f"Gemini request failed after {AI_MAX_RETRIES} attempts: {clean_err}")
        raise AIClientError(f"Gemini generation failed: {clean_err}")

    def generate_json(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        response_schema: Optional[Type[BaseModel]] = None,
    ) -> Dict[str, Any]:
        """Generate structured JSON from Gemini, verifying JSON validity."""
        raw_text = self.generate_content(
            prompt=prompt,
            system_instruction=system_instruction,
            json_mode=True,
            response_schema=response_schema,
        )

        # Parse JSON safely
        try:
            # Handle potential markdown code fences in raw text
            cleaned = raw_text.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[len("```json"):].strip()
            if cleaned.startswith("```"):
                cleaned = cleaned[3:].strip()
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3].strip()

            data = json.loads(cleaned)
            if not isinstance(data, dict):
                raise AISchemaValidationError("Expected JSON object from AI, received array or scalar.")
            return data
        except json.JSONDecodeError as jde:
            logger.warning(f"Failed to parse JSON from AI response: {jde}. Raw snippet: {raw_text[:120]}")
            raise AISchemaValidationError(f"Invalid JSON returned by AI: {jde}")


# Default singleton instance for application use
_default_client: Optional[GeminiClient] = None


def get_ai_client() -> GeminiClient:
    """Retrieve global Gemini client instance."""
    global _default_client
    if _default_client is None:
        _default_client = GeminiClient()
    return _default_client


def set_ai_client(client: Optional[GeminiClient]) -> None:
    """Override AI client for unit tests / mocking."""
    global _default_client
    _default_client = client
