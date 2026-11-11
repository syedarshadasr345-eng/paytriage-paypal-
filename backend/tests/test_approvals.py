"""
PayTriage — Approval Gate & Auth Comprehensive Test Suite
Strictly conforms to phase5.md and RULES.md (§7, §9).
All tests are mock-based with zero live external calls.
"""

from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from backend.auth.config import DEMO_PASSWORD, DEMO_USER, create_session_token
from backend.database import (
    get_approval_by_id,
    get_invoice_by_id,
    insert_invoice,
)
from backend.main import app
from backend.seed import seed_database

TODAY = date(2026, 11, 1)


@pytest.fixture(scope="module", autouse=True)
def init_db():
    seed_database(base_date=TODAY)


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def auth_headers():
    token = create_session_token(DEMO_USER, merchant_id="merchant_demo", role="merchant")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def ai_headers():
    token = create_session_token("gemini_assistant@paytriage.ai", merchant_id="merchant_demo", role="ai")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def other_merchant_headers():
    token = create_session_token("other@merchant.com", merchant_id="merchant_other", role="merchant")
    return {"Authorization": f"Bearer {token}"}


# =============================================================================
# 1. Auth & Login Tests
# =============================================================================

class TestAuthentication:
    def test_login_success(self, client):
        """Valid credentials return a signed bearer token and user profile."""
        res = client.post("/api/auth/login", json={"username": DEMO_USER, "password": DEMO_PASSWORD})
        assert res.status_code == 200
        data = res.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["user"]["email"] == DEMO_USER
        assert data["user"]["role"] == "merchant"

    def test_login_invalid_password(self, client):
        """Invalid credentials return clean 401."""
        res = client.post("/api/auth/login", json={"username": DEMO_USER, "password": "wrong_password"})
        assert res.status_code == 401

    def test_login_fails_clearly_with_missing_config(self, client, monkeypatch):
        """When DEMO_PASSWORD or DEMO_USER or SESSION_SECRET is missing or placeholder, login fails naming the variable."""
        monkeypatch.setenv("DEMO_PASSWORD", "")
        res = client.post("/api/auth/login", json={"username": "any", "password": "any"})
        assert res.status_code == 500
        assert "DEMO_PASSWORD" in res.json()["detail"]

        monkeypatch.setenv("DEMO_PASSWORD", "validpass")
        monkeypatch.setenv("SESSION_SECRET", "your_secret_placeholder")
        res2 = client.post("/api/auth/login", json={"username": "any", "password": "any"})
        assert res2.status_code == 500
        assert "SESSION_SECRET" in res2.json()["detail"]

    def test_login_rate_limiting_enforced(self, client):
        """Rapid login requests exceeding limit return 429."""
        from backend.rate_limit import reset_rate_limits
        reset_rate_limits()
        for _ in range(10):
            res = client.post("/api/auth/login", json={"username": "wrong", "password": "wrong"})
            assert res.status_code == 401
        # 11th request -> 429 Too Many Requests
        res_limit = client.post("/api/auth/login", json={"username": "wrong", "password": "wrong"})
        assert res_limit.status_code == 429
        assert "Rate limit exceeded" in res_limit.json()["detail"]
        reset_rate_limits()

    def test_unauthenticated_blocked(self, client):
        """Calling actions endpoints without token returns 401."""
        res = client.post("/api/actions/propose", json={
            "invoice_id": "INV-MOD-007",
            "action_type": "record_copied_reminder",
            "parameters": {"note": "Test"},
        })
        assert res.status_code == 401


# =============================================================================
# 2. Proposal Validation & Ownership
# =============================================================================

class TestActionProposal:
    def test_wrong_action_type_blocked(self, client, auth_headers):
        """Unsupported action types are strictly rejected with 400."""
        res = client.post("/api/actions/propose", headers=auth_headers, json={
            "invoice_id": "INV-MOD-007",
            "action_type": "unsupported_hacky_action",
            "parameters": {},
        })
        assert res.status_code == 422 or res.status_code == 400

    def test_demo_invoice_paypal_action_blocked(self, client, auth_headers):
        """PayPal operations on demo benchmark invoices are blocked with a clear reason."""
        res = client.post("/api/actions/propose", headers=auth_headers, json={
            "invoice_id": "INV-MOD-007",  # is_demo = True
            "action_type": "paypal_remind_invoice",
            "parameters": {"note": "Reminder text"},
        })
        assert res.status_code == 400
        assert "PayPal actions are disabled for demo benchmark data" in res.json()["detail"]

    def test_demo_invoice_can_use_record_copied_reminder(self, client, auth_headers):
        """Demo invoices CAN use record_copied_reminder."""
        res = client.post("/api/actions/propose", headers=auth_headers, json={
            "invoice_id": "INV-MOD-007",
            "action_type": "record_copied_reminder",
            "parameters": {"text": "Payment reminder text copied to clipboard."},
        })
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "draft"
        assert "approval_id" in data
        assert "hash" in data

    def test_ownership_enforced(self, client, auth_headers, other_merchant_headers):
        """Merchants cannot propose or act upon invoices owned by other merchants."""
        # Insert invoice for merchant_other
        insert_invoice({
            "id": "INV-OTHER-001",
            "invoice_number": "INV-OTHER-001",
            "customer_name": "Other Corp",
            "total_amount": "500.00",
            "outstanding_amount": "500.00",
            "currency": "USD",
            "status": "SENT",
            "due_date": TODAY,
            "merchant_id": "merchant_other",
            "is_demo": False,
        })

        # merchant_demo tries to propose action on INV-OTHER-001
        res = client.post("/api/actions/propose", headers=auth_headers, json={
            "invoice_id": "INV-OTHER-001",
            "action_type": "record_copied_reminder",
            "parameters": {},
        })
        assert res.status_code == 403
        assert "ownership" in res.json()["detail"].lower()


# =============================================================================
# 3. Approval Role Gates (AI cannot approve or execute)
# =============================================================================

class TestApprovalRoleGates:
    def test_ai_can_propose_but_cannot_approve(self, client, ai_headers, auth_headers):
        """AI assistant can propose an action, but cannot approve it."""
        # AI proposes action
        prop_res = client.post("/api/actions/propose", headers=ai_headers, json={
            "invoice_id": "INV-MOD-007",
            "action_type": "record_copied_reminder",
            "parameters": {"text": "AI proposed reminder"},
        })
        assert prop_res.status_code == 200
        appr_id = prop_res.json()["approval_id"]

        # AI tries to approve -> 403 Forbidden
        appr_ai = client.post(f"/api/actions/{appr_id}/approve", headers=ai_headers)
        assert appr_ai.status_code == 403
        assert "cannot approve or execute actions" in appr_ai.json()["detail"]

        # Human merchant approves -> 200 OK
        appr_human = client.post(f"/api/actions/{appr_id}/approve", headers=auth_headers)
        assert appr_human.status_code == 200
        assert appr_human.json()["status"] == "approved"

    def test_ai_cannot_execute(self, client, ai_headers, auth_headers):
        """AI assistant cannot execute an approved action."""
        prop_res = client.post("/api/actions/propose", headers=auth_headers, json={
            "invoice_id": "INV-MOD-007",
            "action_type": "record_copied_reminder",
            "parameters": {"text": "Human reminder"},
        })
        appr_id = prop_res.json()["approval_id"]
        client.post(f"/api/actions/{appr_id}/approve", headers=auth_headers)

        # AI tries to execute -> 403 Forbidden
        exec_ai = client.post(f"/api/actions/{appr_id}/execute", headers=ai_headers, json={
            "action_type": "record_copied_reminder",
            "parameters": {"text": "Human reminder"},
        })
        assert exec_ai.status_code == 403
        assert "cannot approve or execute actions" in exec_ai.json()["detail"]


# =============================================================================
# 4. Integrity, Hash Mismatch, and Duplicate Guards
# =============================================================================

class TestIntegrityAndDuplicateGuards:
    def test_changed_action_after_approval_blocked_409(self, client, auth_headers):
        """Modifying parameters between approval and execution triggers 409 Conflict."""
        prop_res = client.post("/api/actions/propose", headers=auth_headers, json={
            "invoice_id": "INV-MOD-007",
            "action_type": "record_copied_reminder",
            "parameters": {"subject": "Payment Due", "amount": "1800.00"},
        })
        appr_id = prop_res.json()["approval_id"]
        client.post(f"/api/actions/{appr_id}/approve", headers=auth_headers)

        # Tampered execution request (e.g. modified amount)
        exec_res = client.post(f"/api/actions/{appr_id}/execute", headers=auth_headers, json={
            "action_type": "record_copied_reminder",
            "parameters": {"subject": "Payment Due", "amount": "9999.00"},  # Changed!
        })
        assert exec_res.status_code == 409
        assert "Hash mismatch" in exec_res.json()["detail"]

        # Check approval was marked rejected
        appr = get_approval_by_id(appr_id)
        assert appr["status"] == "rejected"

    def test_duplicate_execute_blocked(self, client, auth_headers):
        """Executing an approved action a second time is blocked."""
        prop_res = client.post("/api/actions/propose", headers=auth_headers, json={
            "invoice_id": "INV-MOD-007",
            "action_type": "record_copied_reminder",
            "parameters": {"subject": "Friendly Check-in"},
        })
        appr_id = prop_res.json()["approval_id"]
        client.post(f"/api/actions/{appr_id}/approve", headers=auth_headers)

        # First execution -> 200 OK
        exec_1 = client.post(f"/api/actions/{appr_id}/execute", headers=auth_headers, json={
            "action_type": "record_copied_reminder",
            "parameters": {"subject": "Friendly Check-in"},
        })
        assert exec_1.status_code == 200
        assert exec_1.json()["status"] == "verified"

        # Second execution -> 400 Blocked
        exec_2 = client.post(f"/api/actions/{appr_id}/execute", headers=auth_headers, json={
            "action_type": "record_copied_reminder",
            "parameters": {"subject": "Friendly Check-in"},
        })
        assert exec_2.status_code == 400
        assert "Duplicate execution blocked" in exec_2.json()["detail"]

    def test_expired_approval_blocked(self, client, auth_headers):
        """An expired approval cannot be approved or executed."""
        prop_res = client.post("/api/actions/propose", headers=auth_headers, json={
            "invoice_id": "INV-MOD-007",
            "action_type": "record_copied_reminder",
            "parameters": {"subject": "Old notice"},
        })
        appr_id = prop_res.json()["approval_id"]

        # Manually backdate expiration in DB
        from backend.database import get_db_connection
        conn = get_db_connection()
        with conn:
            conn.execute("UPDATE approvals SET expires_at = ? WHERE id = ?", (
                (datetime.now() - timedelta(days=2)).isoformat(),
                appr_id,
            ))
        conn.close()

        # Approve expired -> 400
        res = client.post(f"/api/actions/{appr_id}/approve", headers=auth_headers)
        assert res.status_code == 400
        assert "expired" in res.json()["detail"].lower()

    def test_approval_state_survives_restart(self, client, auth_headers):
        """Approval records persisted in SQLite database remain durable across server sessions."""
        prop_res = client.post("/api/actions/propose", headers=auth_headers, json={
            "invoice_id": "INV-MOD-007",
            "action_type": "record_copied_reminder",
            "parameters": {"subject": "Persistent reminder test"},
        })
        appr_id = prop_res.json()["approval_id"]
        expected_hash = prop_res.json()["hash"]

        # Fetch directly via database connection simulating fresh server session
        record = get_approval_by_id(appr_id)
        assert record is not None
        assert record["id"] == appr_id
        assert record["hash"] == expected_hash
        assert record["status"] == "draft"
        assert record["invoice_id"] == "INV-MOD-007"
        assert "Persistent reminder test" in record["parameters_json"]


# =============================================================================
# 5. PayPal Execution & Payment Verification
# =============================================================================

class TestPayPalExecutionAndVerification:
    def test_successful_execute_paypal_send_invoice(self, client, auth_headers, monkeypatch):
        """Mocked PayPal send execution verifies invoice status and marks 'verified'."""
        # Insert a Live Sandbox draft invoice
        insert_invoice({
            "id": "INV2-SBX-DRAFT-001",
            "invoice_number": "INV2-SBX-DRAFT-001",
            "customer_name": "Test Client",
            "total_amount": "100.00",
            "outstanding_amount": "100.00",
            "currency": "USD",
            "status": "DRAFT",
            "due_date": TODAY + timedelta(days=10),
            "merchant_id": "merchant_demo",
            "is_demo": False,
        })

        monkeypatch.setattr(
            "backend.actions.service.send_sandbox_invoice",
            lambda inv_id, client=None: {"status": "success"},
        )
        monkeypatch.setattr(
            "backend.actions.service.verify_sandbox_invoice_payment",
            lambda inv_id, client=None: {"invoice_id": inv_id, "status": "SENT", "is_paid": False},
        )

        prop = client.post("/api/actions/propose", headers=auth_headers, json={
            "invoice_id": "INV2-SBX-DRAFT-001",
            "action_type": "paypal_send_invoice",
            "parameters": {"note": "Dispatched invoice"},
        })
        appr_id = prop.json()["approval_id"]
        client.post(f"/api/actions/{appr_id}/approve", headers=auth_headers)

        exec_res = client.post(f"/api/actions/{appr_id}/execute", headers=auth_headers, json={
            "action_type": "paypal_send_invoice",
            "parameters": {"note": "Dispatched invoice"},
        })
        assert exec_res.status_code == 200
        data = exec_res.json()
        assert data["status"] == "verified"
        assert data["verified"] is True

    def test_failed_paypal_verification_marks_failed(self, client, auth_headers, monkeypatch):
        """If verification returns unexpected status or failure, approval status is 'failed'."""
        insert_invoice({
            "id": "INV2-SBX-FAIL-001",
            "invoice_number": "INV2-SBX-FAIL-001",
            "customer_name": "Test Client",
            "total_amount": "100.00",
            "outstanding_amount": "100.00",
            "currency": "USD",
            "status": "DRAFT",
            "due_date": TODAY + timedelta(days=10),
            "merchant_id": "merchant_demo",
            "is_demo": False,
        })

        monkeypatch.setattr(
            "backend.actions.service.send_sandbox_invoice",
            lambda inv_id, client=None: {"status": "success"},
        )
        # Verification claims invoice is still DRAFT (send did not take effect)
        monkeypatch.setattr(
            "backend.actions.service.verify_sandbox_invoice_payment",
            lambda inv_id, client=None: {"invoice_id": inv_id, "status": "DRAFT", "is_paid": False},
        )

        prop = client.post("/api/actions/propose", headers=auth_headers, json={
            "invoice_id": "INV2-SBX-FAIL-001",
            "action_type": "paypal_send_invoice",
            "parameters": {},
        })
        appr_id = prop.json()["approval_id"]
        client.post(f"/api/actions/{appr_id}/approve", headers=auth_headers)

        exec_res = client.post(f"/api/actions/{appr_id}/execute", headers=auth_headers, json={
            "action_type": "paypal_send_invoice",
            "parameters": {},
        })
        assert exec_res.status_code == 200
        data = exec_res.json()
        assert data["status"] == "failed"
        assert data["verified"] is False


# =============================================================================
# 6. Reminder Count Derived from Audit Log
# =============================================================================

class TestReminderCountDerivedFromAuditLog:
    def test_reminder_count_derived_from_activity_logs(self):
        """reminder_count must be dynamically derived from verified executed reminders in activity_logs."""
        from backend.database import (
            get_verified_reminder_count,
            insert_invoice,
            log_activity,
        )

        inv_id = "INV-COUNT-TEST-001"
        insert_invoice({
            "id": inv_id,
            "invoice_number": inv_id,
            "customer_name": "Count Test",
            "total_amount": "1000.00",
            "outstanding_amount": "1000.00",
            "currency": "USD",
            "status": "OVERDUE",
            "due_date": TODAY - timedelta(days=10),
            "reminder_count": 0,
            "is_demo": False,
        })

        # Initially 0 verified reminders in log
        inv_before = get_invoice_by_id(inv_id)
        assert inv_before["reminder_count"] == 0

        # Log 1 verified reminder
        log_activity(inv_id, action_type="paypal_remind", status="verified", details="Dispatched reminder")
        assert get_verified_reminder_count(inv_id) == 1

        inv_after_1 = get_invoice_by_id(inv_id)
        assert inv_after_1["reminder_count"] == 1

        # Log 2nd verified reminder
        log_activity(inv_id, action_type="record_copied_reminder", status="copied", details="Copied reminder")
        assert get_verified_reminder_count(inv_id) == 2

        inv_after_2 = get_invoice_by_id(inv_id)
        assert inv_after_2["reminder_count"] == 2
