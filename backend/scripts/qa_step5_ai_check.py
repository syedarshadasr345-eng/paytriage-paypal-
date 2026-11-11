"""
Step 5 AI Live Check
Invokes explanation for 1 invoice with AI_TIMEOUT_SECONDS=90.
Reports source, latency, fallback reason.
"""

import os
import sys
import time
import pathlib
import json

repo_root = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(repo_root))

from dotenv import load_dotenv
load_dotenv(repo_root / "backend/.env")

# Set AI timeout and live flag
os.environ["AI_TIMEOUT_SECONDS"] = "90"
os.environ["RUN_LIVE_AI"] = "1"
os.environ["AI_FORCE_IPV4"] = "true"

from backend.ai.explainer import explain_invoice_recovery

def main():
    inv_id = "INV-MOD-007"
    print(f"Requesting AI explanation for {inv_id} (Timeout=90s, IPv4=true)...")
    start = time.time()
    result = explain_invoice_recovery(invoice_id=inv_id, question=None)
    latency = time.time() - start

    res_dict = result.model_dump()
    source = res_dict.get("source")
    fallback_reason = res_dict.get("fallback_reason")

    print(f"\n--- STEP 5 AI CHECK RESULT ---")
    print(f"Invoice ID:       {inv_id}")
    print(f"Source:           {source}")
    print(f"Latency:          {latency:.2f}s")
    print(f"Fallback Reason:  {fallback_reason}")
    print(f"Summary:          {res_dict.get('summary')}")
    print(f"Recommended:      {res_dict.get('recommended_action')}")
    print(f"Full JSON:        {json.dumps(res_dict, indent=2)}")

if __name__ == "__main__":
    main()
