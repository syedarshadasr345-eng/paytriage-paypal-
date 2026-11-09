"""
Diagnostic script for PART A: Test Gemini models and capture raw quota/error details.
"""

import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

import httpx
from google import genai
from google.genai import types

from backend.ai.config import GEMINI_MODEL, get_gemini_api_key


def main():
    api_key = get_gemini_api_key()
    print("=" * 60)
    print("PART A: GEMINI MODEL DIAGNOSTICS & RAW QUOTA CHECK")
    print(f"API Key present: {bool(api_key)}")
    print(f"Default Model: {GEMINI_MODEL}")
    print("=" * 60)

    # Build IPv4-forced client
    t = httpx.HTTPTransport(local_address="0.0.0.0")
    http_client = httpx.Client(transport=t, timeout=30.0)
    http_options = types.HttpOptions(httpx_client=http_client, timeout=30000)
    client = genai.Client(api_key=api_key, http_options=http_options)

    # 1. Test gemini-3.8-flash
    print(f"\n1. Testing {GEMINI_MODEL}...")
    start = time.time()
    try:
        resp = client.models.generate_content(
            model=GEMINI_MODEL,
            contents="Say 'OK'",
            config=types.GenerateContentConfig(
                temperature=0.1,
                max_output_tokens=100,
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
        )
        elapsed = time.time() - start
        print(f"SUCCESS in {elapsed:.2f}s: {resp.text.strip()}")
    except Exception as e:
        elapsed = time.time() - start
        print(f"FAILED in {elapsed:.2f}s")
        print(f"Raw Exception Class: {type(e)}")
        print(f"Raw Response Body / Details:\n{e}")

    # 2. List available models
    print("\n2. Calling client.models.list()...")
    try:
        available_models = []
        pager = client.models.list()
        for m in pager:
            name = m.name or ""
            # Filter for models that support generateContent
            supported = m.supported_actions or []
            if "generateContent" in supported or not supported:
                available_models.append(name.replace("models/", ""))
        print(f"Found {len(available_models)} candidate models:")
        print(", ".join(available_models[:15]))
    except Exception as e:
        print(f"Failed to list models: {e}")
        available_models = ["gemini-2.5-flash-lite", "gemini-2.0-flash", "gemini-2.5-flash", "gemini-1.5-flash"]

    # 3. Test candidate models
    candidates = [m for m in available_models if "flash" in m.lower() and m != GEMINI_MODEL]
    if not candidates:
        candidates = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]

    print(f"\n3. Testing alternative flash models: {candidates[:3]}")
    for cand in candidates[:3]:
        print(f"\nTesting model: {cand}...")
        start = time.time()
        try:
            resp = client.models.generate_content(
                model=cand,
                contents="Say 'OK'",
                config=types.GenerateContentConfig(
                    temperature=0.1,
                    max_output_tokens=100,
                ),
            )
            elapsed = time.time() - start
            print(f"  [SUCCESS] {cand} latency: {elapsed:.2f}s -> response: '{resp.text.strip()}'")
            break
        except Exception as e:
            elapsed = time.time() - start
            print(f"  [FAILED] {cand} latency: {elapsed:.2f}s -> error: {e}")


if __name__ == "__main__":
    main()
