"""
Step 3 Live Server Verification Script
Starts uvicorn on 127.0.0.1:8000, performs live HTTP checks, and cleanly shuts down.
"""

import os
import sys
import time
import threading
import pathlib

# Ensure repo root is on sys.path
repo_root = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(repo_root))

import httpx
import uvicorn
from dotenv import load_dotenv

# Ensure environment is loaded from backend/.env
load_dotenv(repo_root / "backend/.env")

demo_user = os.getenv("DEMO_USER")
demo_pass = os.getenv("DEMO_PASSWORD")

from backend.main import app

def run_server(server):
    server.run()

def main():
    config = uvicorn.Config(app=app, host="127.0.0.1", port=8000, log_level="warning")
    server = uvicorn.Server(config)
    t = threading.Thread(target=run_server, args=(server,), daemon=True)
    t.start()

    # Wait for server to start
    client = httpx.Client(base_url="http://127.0.0.1:8000", timeout=10.0)
    for _ in range(30):
        try:
            r = client.get("/api/health")
            if r.status_code == 200:
                break
        except Exception:
            time.sleep(0.2)
    else:
        print("Server failed to start on 127.0.0.1:8000")
        sys.exit(1)

    results = []

    # 1. GET /api/health
    r = client.get("/api/health")
    health_pass = (r.status_code == 200 and r.json().get("status") == "healthy")
    results.append(("GET /api/health", 200, r.status_code, "PASS" if health_pass else "FAIL", r.json()))

    # 2. Wrong login -> 401
    r = client.post("/api/auth/login", json={"username": "wrong_user", "password": "wrong_password"})
    wrong_login_pass = (r.status_code == 401)
    results.append(("Wrong login (401)", 401, r.status_code, "PASS" if wrong_login_pass else "FAIL", r.json()))

    # 3. Demo login -> 200 + token
    r = client.post("/api/auth/login", json={"username": demo_user, "password": demo_pass})
    demo_login_pass = (r.status_code == 200 and "access_token" in r.json())
    token = r.json().get("access_token") if demo_login_pass else None
    results.append(("Demo login (200 + token)", 200, r.status_code, "PASS" if demo_login_pass else "FAIL", f"token_type={r.json().get('token_type')}, user={r.json().get('user', {}).get('email')}"))

    headers = {"Authorization": f"Bearer {token}"} if token else {}

    # 4. 3 Protected endpoints without and with token
    protected_endpoints = [
        ("GET /api/auth/me", "get", "/api/auth/me", None),
        ("GET /api/actions", "get", "/api/actions", None),
        ("POST /api/actions/propose", "post", "/api/actions/propose", {"invoice_id": "INV-MOD-007", "action_type": "record_copied_reminder", "parameters": {"tone": "polite"}})
    ]

    for name, method, path, payload in protected_endpoints:
        # Without token
        if method == "get":
            r_no = client.get(path)
        else:
            r_no = client.post(path, json=payload)
        unauth_pass = (r_no.status_code == 401)
        results.append((f"{name} (without token)", 401, r_no.status_code, "PASS" if unauth_pass else "FAIL", r_no.json().get("detail")))

        # With token
        if method == "get":
            r_with = client.get(path, headers=headers)
        else:
            r_with = client.post(path, json=payload, headers=headers)
        auth_pass = (r_with.status_code in (200, 201))
        results.append((f"{name} (with token)", 200, r_with.status_code, "PASS" if auth_pass else "FAIL", "authenticated successfully"))

    # 5. Unknown invoice ID -> 404 clean JSON
    r = client.get("/api/recovery/invoices/INV-NONEXISTENT")
    unknown_pass = (r.status_code == 404 and "detail" in r.json())
    results.append(("Unknown invoice ID (404)", 404, r.status_code, "PASS" if unknown_pass else "FAIL", r.json()))

    # 6. Invalid date -> 422
    r = client.post("/api/ai/invoices/INV-MOD-007/explain?today=invalid-date")
    invalid_date_pass = (r.status_code == 422)
    results.append(("Invalid date query (422)", 422, r.status_code, "PASS" if invalid_date_pass else "FAIL", "Pydantic date validation rejected malformed date"))

    # 7. CORS rejection on unknown origin
    r_cors_bad = client.options("/api/health", headers={
        "Origin": "http://malicious-site.com",
        "Access-Control-Request-Method": "GET"
    })
    bad_origin_header = r_cors_bad.headers.get("access-control-allow-origin")
    cors_bad_pass = (bad_origin_header != "http://malicious-site.com" and bad_origin_header != "*")

    r_cors_good = client.options("/api/health", headers={
        "Origin": "http://localhost:5173",
        "Access-Control-Request-Method": "GET"
    })
    good_origin_header = r_cors_good.headers.get("access-control-allow-origin")
    cors_good_pass = (good_origin_header == "http://localhost:5173")

    cors_pass = cors_bad_pass and cors_good_pass
    results.append(("CORS unknown origin rejected / localhost allowed", "Omitted / localhost:5173", f"bad='{bad_origin_header}', good='{good_origin_header}'", "PASS" if cors_pass else "FAIL", "Strict CORS policy enforced"))

    # Shutdown
    server.should_exit = True

    print("\n--- STEP 3 LIVE SERVER CHECK RESULTS ---")
    print(f"{'Check':<48} | {'Expected':<12} | {'Actual':<12} | {'Status'}")
    print("-" * 80)
    all_pass = True
    for item in results:
        print(f"{item[0]:<48} | {str(item[1]):<12} | {str(item[2]):<12} | {item[3]}")
        if item[3] != "PASS":
            all_pass = False

    print("\nOverall Status:", "ALL PASSED" if all_pass else "SOME FAILED")
    if not all_pass:
        sys.exit(1)

if __name__ == "__main__":
    main()
