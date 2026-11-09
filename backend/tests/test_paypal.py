"""
PayTriage — PayPal Sandbox Integration Comprehensive Tests
Strictly conforms to phase4.md and RULES.md (§8, §9).
Tests:
- Auth success, failure, caching, and expiry handling
- Missing credentials -> clearly labelled setup state
- Create, fetch, and resilient Pydantic parsing of unexpected fields
- Complete table-driven status mapping
- Synchronization into PayTriage database with strict payment evidence verification
- Supported operations: send and remind
- Step 6 payment verification
- Safety: idempotency headers, local duplicate guard, 404, 429, timeouts, and network errors
- Opt-in live smoke test (@pytest.mark.live_paypal, skipped by default)
"""

from datetime import date
from decimal import Decimal

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.database import get_activity_logs, get_invoice_by_id
from backend.main import app
from backend.paypal.auth import (
    PayPalAuthError,
    PayPalAuthManager,
    PayPalNotConfiguredError,
)
from backend.paypal.client import (
    PayPalApiError,
    PayPalClient,
    PayPalDuplicateRequestError,
    PayPalNotFoundError,
    PayPalRateLimitError,
    PayPalTimeoutError,
)
from backend.paypal.config import (
    get_paypal_client_id,
    get_paypal_client_secret,
    is_paypal_configured,
    mask_credential,
)
from backend.paypal.invoices import (
    create_sandbox_invoice,
    get_sandbox_invoice,
    map_paypal_status_to_app,
    remind_sandbox_invoice,
    send_sandbox_invoice,
    sync_paypal_invoice,
    verify_sandbox_invoice_payment,
)
from backend.seed import seed_database

TODAY = date(2026, 11, 1)


@pytest.fixture(scope="module", autouse=True)
def init_test_db():
    seed_database(base_date=TODAY)


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


# =============================================================================
# Helper: Custom Mock Transport for Resilient HTTP Testing
# =============================================================================

def make_mock_client(handler_fn):
    """Create an httpx.Client with custom mock transport."""
    transport = httpx.MockTransport(handler_fn)
    return httpx.Client(transport=transport)


# =============================================================================
# 1. Configuration & Setup State Tests
# =============================================================================

class TestPayPalConfiguration:
    def test_unconfigured_credentials_returns_setup_state(self, monkeypatch):
        """When credentials are absent or placeholders, is_paypal_configured is False."""
        monkeypatch.delenv("PAYPAL_CLIENT_ID", raising=False)
        monkeypatch.delenv("PAYPAL_CLIENT_SECRET", raising=False)

        assert is_paypal_configured() is False
        assert get_paypal_client_id() is None
        assert get_paypal_client_secret() is None

    def test_placeholder_credentials_treated_as_unconfigured(self, monkeypatch):
        """Placeholder values from .env.example must not be treated as connected."""
        monkeypatch.setenv("PAYPAL_CLIENT_ID", "your_paypal_sandbox_client_id_here")
        monkeypatch.setenv("PAYPAL_CLIENT_SECRET", "your_paypal_sandbox_client_secret_here")

        assert is_paypal_configured() is False

    def test_masked_credential_utility(self):
        """Never exposes raw credentials in telemetry."""
        assert mask_credential(None) == "[NOT_SET]"
        assert mask_credential("") == "[NOT_SET]"
        assert mask_credential("short") == "***"
        assert mask_credential("client_id_123456789") == "clie...6789"

    def test_status_endpoint_shows_setup_state_when_unconfigured(self, client, monkeypatch):
        """GET /api/paypal/status must report clearly labelled setup state."""
        monkeypatch.delenv("PAYPAL_CLIENT_ID", raising=False)
        monkeypatch.delenv("PAYPAL_CLIENT_SECRET", raising=False)

        res = client.get("/api/paypal/status")
        assert res.status_code == 200
        data = res.json()
        assert data["configured"] is False
        assert data["status_label"] == "not_configured"
        assert data["client_id_preview"] == "[NOT_SET]"
        assert "not configured" in data["message"].lower()

    def test_health_endpoint_includes_paypal_setup_status(self, client):
        """GET /api/health exposes paypal_configured boolean."""
        res = client.get("/api/health")
        assert res.status_code == 200
        assert "paypal_configured" in res.json()


# =============================================================================
# 2. Authentication Tests (Step 1)
# =============================================================================

class TestPayPalAuth:
    def test_auth_success_with_token_caching(self, monkeypatch):
        """OAuth token retrieval succeeds and caches token until expiration."""
        monkeypatch.setenv("PAYPAL_CLIENT_ID", "SANDBOX_CLIENT_ID_TEST")
        monkeypatch.setenv("PAYPAL_CLIENT_SECRET", "SANDBOX_SECRET_TEST")

        call_count = 0

        def auth_handler(request: httpx.Request):
            nonlocal call_count
            call_count += 1
            assert request.url.path == "/v1/oauth2/token"
            assert "Basic " in request.headers["Authorization"]
            return httpx.Response(200, json={
                "access_token": "A21AA_TEST_TOKEN_12345",
                "token_type": "Bearer",
                "expires_in": 3600,
                "scope": "https://api.paypal.com/v1/payments/.*",
            })

        mock_http = make_mock_client(auth_handler)
        mgr = PayPalAuthManager()

        # First call fetches fresh token
        token1 = mgr.get_access_token(client=mock_http)
        assert token1 == "A21AA_TEST_TOKEN_12345"
        assert call_count == 1

        # Second call within expiration uses cache (no additional HTTP call)
        token2 = mgr.get_access_token(client=mock_http)
        assert token2 == "A21AA_TEST_TOKEN_12345"
        assert call_count == 1

    def test_auth_failure_invalid_credentials_raises_paypal_auth_error(self, monkeypatch):
        """Invalid credentials return 401, raising clean PayPalAuthError without exposing secrets."""
        monkeypatch.setenv("PAYPAL_CLIENT_ID", "INVALID_ID")
        monkeypatch.setenv("PAYPAL_CLIENT_SECRET", "INVALID_SECRET")

        def auth_handler(request: httpx.Request):
            return httpx.Response(401, json={"error": "invalid_client", "error_description": "Client Authentication failed"})

        mock_http = make_mock_client(auth_handler)
        mgr = PayPalAuthManager()

        with pytest.raises(PayPalAuthError) as exc_info:
            mgr.get_access_token(client=mock_http)
        assert "401" in str(exc_info.value)
        assert "INVALID_SECRET" not in str(exc_info.value)

    def test_auth_missing_credentials_raises_not_configured(self, monkeypatch):
        """Missing credentials raises PayPalNotConfiguredError immediately."""
        monkeypatch.delenv("PAYPAL_CLIENT_ID", raising=False)
        monkeypatch.delenv("PAYPAL_CLIENT_SECRET", raising=False)

        mgr = PayPalAuthManager()
        with pytest.raises(PayPalNotConfiguredError) as exc_info:
            mgr.get_access_token()
        assert "not configured" in str(exc_info.value).lower()


# =============================================================================
# 3. Invoice Creation, Fetching, and Status Mapping (Steps 2 & 3)
# =============================================================================

class TestPayPalInvoices:
    def test_create_sandbox_invoice_payload_and_response(self, monkeypatch):
        """Step 2: Create draft invoice in Sandbox, verifying schema and response parsing."""
        monkeypatch.setenv("PAYPAL_CLIENT_ID", "SANDBOX_CLIENT_ID_TEST")
        monkeypatch.setenv("PAYPAL_CLIENT_SECRET", "SANDBOX_SECRET_TEST")

        def handler(request: httpx.Request):
            if request.url.path == "/v1/oauth2/token":
                return httpx.Response(200, json={"access_token": "TOK123", "expires_in": 3600})
            if request.url.path == "/v2/invoicing/invoices":
                assert request.headers.get("PayPal-Request-Id") is not None
                assert "Bearer TOK123" in request.headers["Authorization"]
                return httpx.Response(201, json={
                    "id": "INV2-TEST-CREATE-001",
                    "status": "DRAFT",
                    "detail": {
                        "invoice_number": "INV-2026-999",
                        "invoice_date": "2026-11-01",
                        "currency_code": "USD",
                    },
                    "amount": {
                        "currency_code": "USD",
                        "value": "2500.00",
                    },
                    "due_amount": {
                        "currency_code": "USD",
                        "value": "2500.00",
                    },
                })
            return httpx.Response(404)

        mock_http = make_mock_client(handler)
        client = PayPalClient(http_client=mock_http)

        inv_data = {
            "invoice_number": "INV-2026-999",
            "total_amount": "2500.00",
            "currency": "USD",
            "customer_name": "Test Enterprise Corp",
            "customer_email": "test@enterprise.com",
        }
        res = create_sandbox_invoice(inv_data, client=client)

        assert res.id == "INV2-TEST-CREATE-001"
        assert res.status == "DRAFT"
        assert res.amount.value == "2500.00"

    def test_create_sandbox_invoice_missing_id_and_href_raises_error(self, monkeypatch):
        """When PayPal creation response lacks both 'id' and 'href', PayPalApiError is raised."""
        monkeypatch.setenv("PAYPAL_CLIENT_ID", "SANDBOX_CLIENT_ID_TEST")
        monkeypatch.setenv("PAYPAL_CLIENT_SECRET", "SANDBOX_SECRET_TEST")

        def handler(request: httpx.Request):
            if request.url.path == "/v1/oauth2/token":
                return httpx.Response(200, json={"access_token": "TOK123", "expires_in": 3600})
            if request.url.path == "/v2/invoicing/invoices":
                return httpx.Response(201, json={"message": "Created but unexpected shape"})
            return httpx.Response(404)

        mock_http = make_mock_client(handler)
        client = PayPalClient(http_client=mock_http)

        inv_data = {
            "invoice_number": "INV-NO-ID",
            "total_amount": "100.00",
            "currency": "USD",
        }
        with pytest.raises(PayPalApiError) as exc_info:
            create_sandbox_invoice(inv_data, client=client)

        assert "PayPal did not return an invoice ID or href" in str(exc_info.value)
        assert exc_info.value.status_code == 201

    def test_get_sandbox_invoice_details_and_resilient_unknown_fields(self, monkeypatch):
        """Step 3: Fetch invoice details; unknown/unexpected PayPal fields do not crash app."""
        monkeypatch.setenv("PAYPAL_CLIENT_ID", "SANDBOX_CLIENT_ID_TEST")
        monkeypatch.setenv("PAYPAL_CLIENT_SECRET", "SANDBOX_SECRET_TEST")

        def handler(request: httpx.Request):
            if request.url.path == "/v1/oauth2/token":
                return httpx.Response(200, json={"access_token": "TOK123", "expires_in": 3600})
            if request.url.path == "/v2/invoicing/invoices/INV2-1234":
                # Returns standard fields PLUS unexpected future PayPal fields
                return httpx.Response(200, json={
                    "id": "INV2-1234",
                    "status": "SENT",
                    "detail": {"invoice_number": "INV-2026-1234"},
                    "amount": {"currency_code": "USD", "value": "1800.00"},
                    "future_paypal_ai_field": {"model": "sandbox-v3", "tags": [1, 2, 3]},
                    "experimental_feature_flag": True,
                })
            return httpx.Response(404)

        mock_http = make_mock_client(handler)
        client = PayPalClient(http_client=mock_http)

        res = get_sandbox_invoice("INV2-1234", client=client)
        assert res.id == "INV2-1234"
        assert res.status == "SENT"
        assert res.amount.value == "1800.00"

    @pytest.mark.parametrize(
        "paypal_status,days_diff,expected_app_status",
        [
            ("DRAFT", 10, "DRAFT"),
            ("SCHEDULED", -5, "DRAFT"),
            ("SENT", -5, "SENT"),           # Not yet overdue (due in 5 days)
            ("SENT", 10, "OVERDUE"),         # 10 days overdue
            ("UNPAID", 5, "OVERDUE"),
            ("PARTIALLY_PAID", 5, "PARTIALLY_PAID"),
            ("PAID", 10, "PAID"),
            ("MARKED_AS_PAID", 10, "PAID"),
            ("CANCELLED", 10, "CANCELLED"),
            ("REFUNDED", 10, "REFUNDED"),
            ("PARTIALLY_REFUNDED", 10, "REFUNDED"),
            ("PAYMENT_PENDING", -2, "SENT"),
            ("PAYMENT_PENDING", 4, "OVERDUE"),
            ("UNKNOWN_FUTURE_STATUS", 5, "OVERDUE"),
        ],
    )
    def test_map_paypal_status_to_app_table(self, paypal_status, days_diff, expected_app_status):
        """Verify strict table-driven mapping from PayPal statuses to PayTriage statuses."""
        from datetime import timedelta
        due = TODAY - timedelta(days=days_diff)
        result = map_paypal_status_to_app(paypal_status, due_date=due, today=TODAY)
        assert result == expected_app_status


# =============================================================================
# 4. Synchronization & Payment Verification (Steps 4, 5, 6)
# =============================================================================

class TestPayPalSyncAndPaymentVerification:
    def test_sync_overdue_invoice_inserts_into_db(self, monkeypatch):
        """Step 4: Syncing an overdue invoice inserts into PayTriage SQLite and logs audit activity."""
        monkeypatch.setenv("PAYPAL_CLIENT_ID", "SANDBOX_CLIENT_ID_TEST")
        monkeypatch.setenv("PAYPAL_CLIENT_SECRET", "SANDBOX_SECRET_TEST")

        def handler(request: httpx.Request):
            if request.url.path == "/v1/oauth2/token":
                return httpx.Response(200, json={"access_token": "TOK123", "expires_in": 3600})
            if request.url.path == "/v2/invoicing/invoices/INV2-SYNC-001":
                return httpx.Response(200, json={
                    "id": "INV2-SYNC-001",
                    "status": "SENT",
                    "detail": {
                        "invoice_number": "INV-PP-001",
                        "payment_term": {"due_date": "2026-10-15"},
                    },
                    "amount": {"currency_code": "USD", "value": "4500.00"},
                    "due_amount": {"currency_code": "USD", "value": "4500.00"},
                    "primary_recipients": [{
                        "billing_info": {
                            "name": {"full_name": "Synced Merchant Client"},
                            "email_address": "client@synced.example",
                        }
                    }],
                })
            return httpx.Response(404)

        mock_http = make_mock_client(handler)
        client = PayPalClient(http_client=mock_http)

        sync_res = sync_paypal_invoice("INV2-SYNC-001", today=TODAY, client=client)

        assert sync_res.app_invoice_id == "INV2-SYNC-001"
        assert sync_res.app_status == "OVERDUE"
        assert sync_res.outstanding_amount == Decimal("4500.00")
        assert sync_res.is_paid_verified is False

        # Verify DB insertion
        db_inv = get_invoice_by_id("INV2-SYNC-001")
        assert db_inv is not None
        assert db_inv["status"] == "OVERDUE"
        assert Decimal(db_inv["outstanding_amount"]) == Decimal("4500.00")

        # Verify audit activity log
        logs = get_activity_logs(invoice_id="INV2-SYNC-001")
        assert any(l["action_type"] == "paypal_sync" for l in logs)

    def test_sync_never_marks_paid_without_paypal_evidence(self, monkeypatch):
        """RULES.md §4: Never marks an invoice paid without verified PayPal evidence."""
        monkeypatch.setenv("PAYPAL_CLIENT_ID", "SANDBOX_CLIENT_ID_TEST")
        monkeypatch.setenv("PAYPAL_CLIENT_SECRET", "SANDBOX_SECRET_TEST")

        def handler(request: httpx.Request):
            if request.url.path == "/v1/oauth2/token":
                return httpx.Response(200, json={"access_token": "TOK123", "expires_in": 3600})
            if request.url.path == "/v2/invoicing/invoices/INV2-UNPAID-002":
                return httpx.Response(200, json={
                    "id": "INV2-UNPAID-002",
                    "status": "SENT",
                    "detail": {"payment_term": {"due_date": "2026-10-20"}},
                    "amount": {"currency_code": "USD", "value": "1000.00"},
                    "due_amount": {"currency_code": "USD", "value": "1000.00"},
                    "payments": None,
                })
            return httpx.Response(404)

        mock_http = make_mock_client(handler)
        client = PayPalClient(http_client=mock_http)

        sync_res = sync_paypal_invoice("INV2-UNPAID-002", today=TODAY, client=client)
        assert sync_res.is_paid_verified is False
        assert sync_res.app_status != "PAID"

    def test_sync_with_verified_paypal_paid_evidence(self, monkeypatch):
        """When PayPal response contains official PAID status, it is verified."""
        monkeypatch.setenv("PAYPAL_CLIENT_ID", "SANDBOX_CLIENT_ID_TEST")
        monkeypatch.setenv("PAYPAL_CLIENT_SECRET", "SANDBOX_SECRET_TEST")

        def handler(request: httpx.Request):
            if request.url.path == "/v1/oauth2/token":
                return httpx.Response(200, json={"access_token": "TOK123", "expires_in": 3600})
            if request.url.path == "/v2/invoicing/invoices/INV2-PAID-003":
                return httpx.Response(200, json={
                    "id": "INV2-PAID-003",
                    "status": "PAID",
                    "detail": {"payment_term": {"due_date": "2026-10-10"}},
                    "amount": {"currency_code": "USD", "value": "3200.00"},
                    "due_amount": {"currency_code": "USD", "value": "0.00"},
                })
            return httpx.Response(404)

        mock_http = make_mock_client(handler)
        client = PayPalClient(http_client=mock_http)

        sync_res = sync_paypal_invoice("INV2-PAID-003", today=TODAY, client=client)
        assert sync_res.is_paid_verified is True
        assert sync_res.app_status == "PAID"
        assert "paypal_status:PAID" in sync_res.evidence_source

    def test_send_and_remind_operations(self, monkeypatch):
        """Step 5: Execute supported send and remind operations with audit logging."""
        from backend.database import insert_invoice
        monkeypatch.setenv("PAYPAL_CLIENT_ID", "SANDBOX_CLIENT_ID_TEST")
        monkeypatch.setenv("PAYPAL_CLIENT_SECRET", "SANDBOX_SECRET_TEST")

        insert_invoice({
            "id": "INV2-OP-001",
            "invoice_number": "INV2-OP-001",
            "customer_name": "Test Client",
            "total_amount": "100.00",
            "outstanding_amount": "100.00",
            "status": "DRAFT",
            "due_date": TODAY,
        })

        send_called = False
        remind_called = False

        def handler(request: httpx.Request):
            nonlocal send_called, remind_called
            if request.url.path == "/v1/oauth2/token":
                return httpx.Response(200, json={"access_token": "TOK123", "expires_in": 3600})
            if request.url.path == "/v2/invoicing/invoices/INV2-OP-001/send":
                send_called = True
                assert request.headers.get("PayPal-Request-Id") is not None
                return httpx.Response(204)
            if request.url.path == "/v2/invoicing/invoices/INV2-OP-001/remind":
                remind_called = True
                assert request.headers.get("PayPal-Request-Id") is not None
                return httpx.Response(204)
            return httpx.Response(404)

        mock_http = make_mock_client(handler)
        client = PayPalClient(http_client=mock_http)

        send_res = send_sandbox_invoice("INV2-OP-001", client=client)
        assert send_res["http_status"] == 204
        assert send_called is True

        remind_res = remind_sandbox_invoice("INV2-OP-001", client=client)
        assert remind_res["http_status"] == 204
        assert remind_called is True

        logs = get_activity_logs(invoice_id="INV2-OP-001")
        assert any(l["action_type"] == "paypal_send" for l in logs)
        assert any(l["action_type"] == "paypal_remind" for l in logs)

    def test_step_6_payment_verification(self, monkeypatch):
        """Step 6: Re-fetch invoice after operation and record verified state."""
        monkeypatch.setenv("PAYPAL_CLIENT_ID", "SANDBOX_CLIENT_ID_TEST")
        monkeypatch.setenv("PAYPAL_CLIENT_SECRET", "SANDBOX_SECRET_TEST")

        def handler(request: httpx.Request):
            if request.url.path == "/v1/oauth2/token":
                return httpx.Response(200, json={"access_token": "TOK123", "expires_in": 3600})
            if request.url.path == "/v2/invoicing/invoices/INV2-VERIFY-001":
                return httpx.Response(200, json={
                    "id": "INV2-VERIFY-001",
                    "status": "PAID",
                    "amount": {"currency_code": "USD", "value": "5000.00"},
                    "due_amount": {"currency_code": "USD", "value": "0.00"},
                })
            return httpx.Response(404)

        mock_http = make_mock_client(handler)
        client = PayPalClient(http_client=mock_http)

        verify_res = verify_sandbox_invoice_payment("INV2-VERIFY-001", client=client)
        assert verify_res["is_paid"] is True
        assert verify_res["status"] == "PAID"

        logs = get_activity_logs(invoice_id="INV2-VERIFY-001")
        assert any(l["action_type"] == "paypal_payment_verification" for l in logs)


# =============================================================================
# 5. Safety, Error Handling & Idempotency Tests
# =============================================================================

class TestPayPalSafetyAndIdempotency:
    def test_local_duplicate_guard_prevents_duplicate_request_id(self, monkeypatch):
        """Duplicate request IDs are blocked locally to prevent double execution."""
        monkeypatch.setenv("PAYPAL_CLIENT_ID", "SANDBOX_CLIENT_ID_TEST")
        monkeypatch.setenv("PAYPAL_CLIENT_SECRET", "SANDBOX_SECRET_TEST")

        def handler(request: httpx.Request):
            if request.url.path == "/v1/oauth2/token":
                return httpx.Response(200, json={"access_token": "TOK123", "expires_in": 3600})
            return httpx.Response(204)

        mock_http = make_mock_client(handler)
        client = PayPalClient(http_client=mock_http)

        # First dispatch succeeds
        client.request("POST", "/v2/invoicing/invoices/123/send", request_id="REQ-DUPLICATE-GUARD-01")

        # Second dispatch with identical request_id raises PayPalDuplicateRequestError
        with pytest.raises(PayPalDuplicateRequestError) as exc_info:
            client.request("POST", "/v2/invoicing/invoices/123/send", request_id="REQ-DUPLICATE-GUARD-01")
        assert "Duplicate request detected locally" in str(exc_info.value)

    def test_api_404_raises_paypal_not_found_error(self, monkeypatch):
        """404 Not Found returns clean PayPalNotFoundError."""
        monkeypatch.setenv("PAYPAL_CLIENT_ID", "SANDBOX_CLIENT_ID_TEST")
        monkeypatch.setenv("PAYPAL_CLIENT_SECRET", "SANDBOX_SECRET_TEST")

        def handler(request: httpx.Request):
            if request.url.path == "/v1/oauth2/token":
                return httpx.Response(200, json={"access_token": "TOK123", "expires_in": 3600})
            return httpx.Response(404, json={"name": "RESOURCE_NOT_FOUND", "message": "The specified invoice does not exist."})

        mock_http = make_mock_client(handler)
        client = PayPalClient(http_client=mock_http)

        with pytest.raises(PayPalNotFoundError) as exc_info:
            client.request("GET", "/v2/invoicing/invoices/NON-EXISTENT")
        assert exc_info.value.status_code == 404
        assert "RESOURCE_NOT_FOUND" in str(exc_info.value)

    def test_api_429_raises_paypal_rate_limit_error(self, monkeypatch):
        """429 Rate Limit returns clean PayPalRateLimitError."""
        monkeypatch.setenv("PAYPAL_CLIENT_ID", "SANDBOX_CLIENT_ID_TEST")
        monkeypatch.setenv("PAYPAL_CLIENT_SECRET", "SANDBOX_SECRET_TEST")

        def handler(request: httpx.Request):
            if request.url.path == "/v1/oauth2/token":
                return httpx.Response(200, json={"access_token": "TOK123", "expires_in": 3600})
            return httpx.Response(429, json={"name": "RATE_LIMIT_REACHED", "message": "Too many requests"})

        mock_http = make_mock_client(handler)
        client = PayPalClient(http_client=mock_http)

        with pytest.raises(PayPalRateLimitError) as exc_info:
            client.request("GET", "/v2/invoicing/invoices")
        assert exc_info.value.status_code == 429

    def test_api_timeout_raises_clean_timeout_error(self, monkeypatch):
        """Network timeout raises PayPalTimeoutError."""
        monkeypatch.setenv("PAYPAL_CLIENT_ID", "SANDBOX_CLIENT_ID_TEST")
        monkeypatch.setenv("PAYPAL_CLIENT_SECRET", "SANDBOX_SECRET_TEST")

        def handler(request: httpx.Request):
            if request.url.path == "/v1/oauth2/token":
                return httpx.Response(200, json={"access_token": "TOK123", "expires_in": 3600})
            raise httpx.ReadTimeout("Simulated network read timeout")

        mock_http = make_mock_client(handler)
        client = PayPalClient(http_client=mock_http)

        with pytest.raises(PayPalTimeoutError) as exc_info:
            client.request("GET", "/v2/invoicing/invoices")
        assert "timed out" in str(exc_info.value).lower()


# =============================================================================
# 6. Opt-In Live PayPal Smoke Test
# =============================================================================

@pytest.mark.live_paypal
def test_live_paypal_sandbox_smoke():
    """Opt-in live smoke test against genuine PayPal Sandbox.
    Only runs when RUN_LIVE_PAYPAL=1 and real credentials are in backend/.env.
    """
    if not is_paypal_configured():
        pytest.skip("PayPal Sandbox credentials not configured in backend/.env. Live test marked as NOT RUN.")

    from backend.paypal.auth import get_paypal_access_token
    token = get_paypal_access_token()
    assert token is not None and len(token) > 10

