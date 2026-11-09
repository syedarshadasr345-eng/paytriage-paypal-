"""
PayTriage AI — AI Client Wrapper for Google Gemini
Strictly conforms to phase3.md and RULES.md (§4, §6).
Wraps Google GenAI SDK with timeouts, retries, safe logging, and mockability.
"""

import json
import logging
import time
from typing import Any

import httpx
from pydantic import BaseModel

from backend.ai.config import (
    AI_FORCE_IPV4,
    AI_MAX_RETRIES,
    AI_TIMEOUT_SECONDS,
    GEMINI_MODEL,
    get_gemini_api_key,
    redact_sensitive_data,
)

logger = logging.getLogger("paytriage.ai.client")


class AIClientError(Exception):
    """Base exception for AI client failures."""


class AITimeoutError(AIClientError):
    """Raised when the AI provider request times out."""


class AIProviderUnavailableError(AIClientError):
    """Raised when the AI provider API key is not configured or service is unreachable."""


class AISchemaValidationError(AIClientError):
    """Raised when the AI returns output that does not match the expected schema."""


class GeminiClient:
    """Wrapper for Google Gemini API via official google-genai SDK.
    Supports timeouts, retries, safe telemetry, and test mocking.
    """

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self._api_key = api_key or get_gemini_api_key()
        self.model = model or GEMINI_MODEL
        self._sdk_client = None

    def _get_sdk_client(self):
        """Lazy-initialize google-genai client with request timeout."""
        if not self._api_key:
            raise AIProviderUnavailableError(
                "GEMINI_API_KEY is not configured in backend/.env or environment. "
                "Operating in deterministic template fallback mode."
            )
        if self._sdk_client is None:
            try:
                from google import genai
                from google.genai import types
                timeout_ms = int(AI_TIMEOUT_SECONDS * 1000)
                
                # Check current google-genai SDK docs: types.HttpOptions supports custom httpx_client.
                # Force IPv4 using local_address="0.0.0.0" if AI_FORCE_IPV4 is enabled.
                http_client = None
                if AI_FORCE_IPV4:
                    transport = httpx.HTTPTransport(local_address="0.0.0.0")
                    http_client = httpx.Client(transport=transport, timeout=AI_TIMEOUT_SECONDS)

                http_options = types.HttpOptions(
                    timeout=timeout_ms,
                    httpx_client=http_client,
                )
                self._sdk_client = genai.Client(
                    api_key=self._api_key,
                    http_options=http_options,
                )
            except Exception as e:
                clean_err = redact_sensitive_data(str(e))
                logger.error(f"Failed to initialize google-genai client: {clean_err}")
                raise AIProviderUnavailableError(f"Failed to initialize Gemini SDK client: {clean_err}")
        return self._sdk_client

    def generate_content(
        self,
        prompt: str,
        system_instruction: str | None = None,
        json_mode: bool = True,
        response_schema: type[BaseModel] | None = None,
    ) -> str:
        """Call Gemini model with timeouts, retries, and error redaction.
        Returns the raw string output from the model.
        """
        sdk_client = self._get_sdk_client()

        from google.genai import types

        timeout_ms = int(AI_TIMEOUT_SECONDS * 1000)
        http_options = types.HttpOptions(timeout=timeout_ms)

        config_kwargs: dict[str, Any] = {
            "temperature": 0.2,  # Low temperature for grounded recovery intelligence
            "http_options": http_options,
        }

        if system_instruction:
            config_kwargs["system_instruction"] = system_instruction

        if json_mode:
            config_kwargs["response_mime_type"] = "application/json"
            if response_schema:
                config_kwargs["response_schema"] = response_schema

        config = types.GenerateContentConfig(**config_kwargs)

        start_time = time.time()
        max_attempts = min(3, max(1, AI_MAX_RETRIES + 2))
        last_error = None

        for attempt in range(1, max_attempts + 1):
            try:
                logger.info(f"Dispatching Gemini request (model={self.model}, attempt={attempt}/{max_attempts}, timeout={AI_TIMEOUT_SECONDS}s)")
                
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

                # Check if failure is due to request timeout or deadline expiration
                is_timeout = (
                    isinstance(exc, (TimeoutError, httpx.TimeoutException))
                    or "timeout" in clean_msg.lower()
                    or "timed out" in clean_msg.lower()
                    or "deadline" in clean_msg.lower()
                )
                if is_timeout:
                    logger.error(f"Gemini request timed out after {AI_TIMEOUT_SECONDS}s: {clean_msg}")
                    raise AITimeoutError(f"Gemini request timed out after {AI_TIMEOUT_SECONDS}s: {clean_msg}")

                # Retry ONLY for 503 (high demand) and 429 (quota/rate limit)
                is_transient = "503" in clean_msg or "429" in clean_msg or "unavailable" in clean_msg.lower()
                elapsed = time.time() - start_time
                remaining_time = AI_TIMEOUT_SECONDS - elapsed

                if is_transient and attempt < max_attempts and remaining_time > 2.0:
                    backoff = min(1.5 * attempt, remaining_time - 0.5)
                    logger.info(f"Transient error ({clean_msg[:60]}). Backing off {backoff:.1f}s before retry...")
                    time.sleep(backoff)
                else:
                    break

        # All retries exhausted
        clean_err = redact_sensitive_data(str(last_error))
        logger.error(f"Gemini request failed: {clean_err}")
        raise AIClientError(f"Gemini generation failed: {clean_err}")

    def generate_json(
        self,
        prompt: str,
        system_instruction: str | None = None,
        response_schema: type[BaseModel] | None = None,
    ) -> dict[str, Any]:
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
_default_client: GeminiClient | None = None


def get_ai_client() -> GeminiClient:
    """Retrieve global Gemini client instance."""
    global _default_client
    if _default_client is None:
        _default_client = GeminiClient()
    return _default_client


def set_ai_client(client: GeminiClient | None) -> None:
    """Override AI client for unit tests / mocking."""
    global _default_client
    _default_client = client
