from datetime import date
from decimal import Decimal
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.seed import seed_database
from backend.recovery.config import SCORING_VERSION

# Fixed evaluation reference date for deterministic testing
TODAY = date(2026, 11, 1)


@pytest.fixture(scope="module", autouse=True)
def setup_test_db():
    """Ensure database has the 16 demo benchmark records relative to TODAY."""
    seed_database(base_date=TODAY)


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


class TestHealthAndRootEndpoints:
    def test_health_check(self, client):
        res = client.get("/api/health")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "healthy"
        assert data["scoring_version"] == SCORING_VERSION

    def test_root_endpoint(self, client):
        res = client.get("/")
        assert res.status_code == 200
        assert "queue_url" in res.json()


class TestRecoveryQueueEndpoint:
    def test_queue_excludes_not_due_by_default(self, client):
        """Default queue must exclude not-yet-due invoices (days_overdue <= 0)."""
        res = client.get(f"/api/recovery/queue?today={TODAY.isoformat()}")
        assert res.status_code == 200
        data = res.json()
        items = data["items"]
        invoice_ids = [it["id"] for it in items]

        # INV-NOTDUE-005 and INV-DRAFT-004 are not-yet-due (due in 5 and 10 days)
        assert "INV-NOTDUE-005" not in invoice_ids
        assert "INV-DRAFT-004" not in invoice_ids
        for it in items:
            assert it["days_overdue"] > 0

    def test_queue_includes_not_due_when_flag_is_true(self, client):
        """When include_not_due=True, not-yet-due invoices are included."""
        res = client.get(f"/api/recovery/queue?include_not_due=true&today={TODAY.isoformat()}")
        assert res.status_code == 200
        data = res.json()
        invoice_ids = [it["id"] for it in data["items"]]
        assert "INV-NOTDUE-005" in invoice_ids

    def test_queue_filter_by_priority(self, client):
        """Filter queue by priority CRITICAL."""
        res = client.get(f"/api/recovery/queue?priority=CRITICAL&today={TODAY.isoformat()}")
        assert res.status_code == 200
        data = res.json()
        for it in data["items"]:
            assert it["priority"] == "CRITICAL"

    def test_queue_filter_by_action(self, client):
        """Filter queue by recommended action send_firm_followup."""
        res = client.get(f"/api/recovery/queue?action=send_firm_followup&today={TODAY.isoformat()}")
        assert res.status_code == 200
        data = res.json()
        for it in data["items"]:
            assert it["recommended_action"] == "send_firm_followup"

    def test_queue_sorting_by_score_descending(self, client):
        """Verify sorting by score desc puts highest scores first and None last."""
        res = client.get(f"/api/recovery/queue?sort_by=score&sort_dir=desc&today={TODAY.isoformat()}")
        assert res.status_code == 200
        data = res.json()
        scores = [it["score"] for it in data["items"] if it["score"] is not None]
        # Should be monotonically non-increasing
        assert scores == sorted(scores, reverse=True)

    def test_queue_summary_metrics(self, client):
        """Verify computed summary totals in queue response."""
        res = client.get(f"/api/recovery/queue?today={TODAY.isoformat()}")
        assert res.status_code == 200
        data = res.json()
        assert data["total_count"] > 0
        assert data["actionable_count"] > 0
        assert Decimal(str(data["total_outstanding_usd"])) > Decimal("0.00")


class TestRecoveryInvoiceDetailEndpoint:
    def test_get_valid_invoice_detail(self, client):
        """Retrieve detail for severely overdue invoice INV-SEV-009."""
        res = client.get(f"/api/recovery/invoices/INV-SEV-009?today={TODAY.isoformat()}")
        assert res.status_code == 200
        data = res.json()
        inv = data["invoice"]
        assert inv["id"] == "INV-SEV-009"
        # 40 (days=35) + 25 ($7500) + 12 (reminders=2) + 15 (history=late) = 92
        assert inv["score"] == 92
        assert inv["priority"] == "CRITICAL"
        assert inv["recommended_action"] == "send_firm_followup"
        assert len(data["contributing_factors"]) >= 3
        assert data["scoring_version"] == SCORING_VERSION

    def test_missing_history_invoice_has_assumption_flag(self, client):
        """Invoice INV-NOHIST-011 must carry is_assumption=True on history factor."""
        res = client.get(f"/api/recovery/invoices/INV-NOHIST-011?today={TODAY.isoformat()}")
        assert res.status_code == 200
        data = res.json()
        factors = data["contributing_factors"]
        hist_factor = next(f for f in factors if f["factor_name"] == "customer_history_unavailable")
        assert hist_factor["is_assumption"] is True
        assert hist_factor["points"] == 5
        assert "customer_payment_history" in data["invoice"]["unavailable_information"]

    def test_get_nonexistent_invoice_returns_404(self, client):
        """Requesting an unknown ID returns HTTP 404."""
        res = client.get("/api/recovery/invoices/NON-EXISTENT-ID")
        assert res.status_code == 404
        assert "not found" in res.json()["detail"].lower()


class TestRecoveryInvoiceStrategiesEndpoint:
    def test_get_strategies_for_invoice(self, client):
        """Retrieve strategy comparison for INV-SEV-009."""
        res = client.get(f"/api/recovery/invoices/INV-SEV-009/strategies?today={TODAY.isoformat()}")
        assert res.status_code == 200
        data = res.json()
        assert data["invoice_id"] == "INV-SEV-009"
        assert len(data["strategies"]) == 4

        for strat in data["strategies"]:
            assert strat["classification"] in ["recommended", "applicable", "not_recommended"]
            assert len(strat["advantages"]) > 0
            assert len(strat["limitations"]) > 0
            assert "%" not in strat["advantages"]
            assert "%" not in strat["limitations"]

    def test_strategies_nonexistent_invoice_returns_404(self, client):
        res = client.get("/api/recovery/invoices/NON-EXISTENT-ID/strategies")
        assert res.status_code == 404


class TestQueryDateValidation:
    """Verifies that invalid 'today' query parameter returns a clean 422 Unprocessable Entity."""

    def test_invalid_today_in_queue_returns_422(self, client):
        res = client.get("/api/recovery/queue?today=invalid-date")
        assert res.status_code == 422
        errors = res.json()["detail"]
        assert any("date" in str(e).lower() for e in errors)

    def test_invalid_today_in_explain_returns_422(self, client):
        res = client.post("/api/ai/invoices/INV-SEV-009/explain?today=not-a-date")
        assert res.status_code == 422
        errors = res.json()["detail"]
        assert any("date" in str(e).lower() for e in errors)

    def test_invalid_today_in_assistant_returns_422(self, client):
        res = client.post("/api/ai/assistant?today=2026-99-99", json={"message": "Show overdue invoices"})
        assert res.status_code == 422
        errors = res.json()["detail"]
        assert any("date" in str(e).lower() for e in errors)


class TestCORSRestrictions:
    """Verifies CORS restrictions: configurable origins allowed, no wildcard, unknown origins blocked."""

    def test_allowed_origin_returns_cors_headers(self, client):
        res = client.get("/api/health", headers={"Origin": "http://localhost:5173"})
        assert res.status_code == 200
        assert res.headers.get("access-control-allow-origin") == "http://localhost:5173"

    def test_alternate_allowed_origin_returns_cors_headers(self, client):
        res = client.get("/api/health", headers={"Origin": "http://127.0.0.1:5173"})
        assert res.status_code == 200
        assert res.headers.get("access-control-allow-origin") == "http://127.0.0.1:5173"

    def test_disallowed_origin_rejected_without_allow_origin_header(self, client):
        res = client.get("/api/health", headers={"Origin": "http://malicious-site.example.com"})
        assert res.status_code == 200
        assert "access-control-allow-origin" not in res.headers

    def test_cors_never_returns_wildcard(self, client):
        res = client.get("/api/health", headers={"Origin": "http://localhost:5173"})
        assert res.headers.get("access-control-allow-origin") != "*"
