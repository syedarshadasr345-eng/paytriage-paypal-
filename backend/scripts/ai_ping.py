"""
PayTriage AI — Standalone Diagnostic Ping Script
Tests connectivity to Google Gemini API with timeout 60s.
Compares IPv4-forced vs default DNS resolution.
Applies minimal thinking budget (0) and max_output_tokens=1024 for gemini-3.8-flash.
NEVER prints or leaks API keys.
"""

import os
import sys
import time
import socket
from pathlib import Path

# Add project root to path
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

from backend.ai.config import get_gemini_api_key, GEMINI_MODEL


def ping_gemini(force_ipv4: bool = False, model_name: str = GEMINI_MODEL) -> dict:
    """Execute a single ping against Gemini API."""
    orig_getaddrinfo = socket.getaddrinfo

    if force_ipv4:
        def ipv4_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
            return orig_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)
        socket.getaddrinfo = ipv4_getaddrinfo

    api_key = get_gemini_api_key()
    if not api_key:
        return {
            "mode": "IPv4-forced" if force_ipv4 else "Default",
            "model": model_name,
            "success": False,
            "elapsed_seconds": 0.0,
            "error": "GEMINI_API_KEY is not configured in backend/.env",
        }

    from google import genai
    from google.genai import types

    start_time = time.time()
    try:
        http_options = types.HttpOptions(timeout=60000)  # 60s timeout in ms
        client = genai.Client(api_key=api_key, http_options=http_options)

        config = types.GenerateContentConfig(
            temperature=0.1,
            max_output_tokens=1024,
            thinking_config=types.ThinkingConfig(thinking_budget=0),  # Minimal thinking
            http_options=http_options,
        )

        resp = client.models.generate_content(
            model=model_name,
            contents="Respond with exactly: 'PayTriage Gemini Ping OK'",
            config=config,
        )
        elapsed = time.time() - start_time
        return {
            "mode": "IPv4-forced" if force_ipv4 else "Default",
            "model": model_name,
            "success": True,
            "elapsed_seconds": round(elapsed, 2),
            "response": resp.text.strip() if resp and resp.text else "[Empty]",
        }

    except Exception as exc:
        elapsed = time.time() - start_time
        err_str = str(exc)
        # Redact key if by any chance present in error
        if api_key in err_str:
            err_str = err_str.replace(api_key, "[REDACTED_KEY]")
        return {
            "mode": "IPv4-forced" if force_ipv4 else "Default",
            "model": model_name,
            "success": False,
            "elapsed_seconds": round(elapsed, 2),
            "error": err_str,
        }
    finally:
        socket.getaddrinfo = orig_getaddrinfo


def main():
    print("=" * 60)
    print("PayTriage AI Diagnostic Ping (Timeout: 60s)")
    print("=" * 60)
    api_key = get_gemini_api_key()
    print(f"API Key Configured: {bool(api_key)}")
    print(f"Target Model: {GEMINI_MODEL}")
    print()

    # 1. Test with default DNS
    print("1. Testing with Default DNS...")
    res_default = ping_gemini(force_ipv4=False)
    print(f"   Model: {res_default['model']}")
    print(f"   Elapsed: {res_default['elapsed_seconds']}s")
    if res_default['success']:
        print(f"   Response: {res_default['response']}")
    else:
        print(f"   Error: {res_default['error']}")
    print()

    # 2. Test with IPv4-forced
    print("2. Testing with IPv4-Forced DNS...")
    res_ipv4 = ping_gemini(force_ipv4=True)
    print(f"   Model: {res_ipv4['model']}")
    print(f"   Elapsed: {res_ipv4['elapsed_seconds']}s")
    if res_ipv4['success']:
        print(f"   Response: {res_ipv4['response']}")
    else:
        print(f"   Error: {res_ipv4['error']}")
    print()

    print("=" * 60)
    print("Comparison Summary:")
    print(f"Default DNS:   {'SUCCESS' if res_default['success'] else 'FAILED'} ({res_default['elapsed_seconds']}s)")
    print(f"IPv4-Forced:   {'SUCCESS' if res_ipv4['success'] else 'FAILED'} ({res_ipv4['elapsed_seconds']}s)")
    print("=" * 60)


if __name__ == "__main__":
    main()
