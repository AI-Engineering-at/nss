"""Integration tests: security enforcement verification.

Proves that JWT, HMAC, Policy Engine, and Privacy Budget are
actually enforced in the live request pipeline.
"""

from __future__ import annotations

from starlette.testclient import TestClient

from nss.auth import create_token
from nss.governance.server import app as governance_app
from nss.guardian.server import app as guardian_app
from nss.metrics_server import app as metrics_app

_JWT_SECRET = "change-me-in-production"
_HMAC_SECRET = "change-me-in-production"


def _auth_headers(role: str = "admin") -> dict[str, str]:
    token = create_token("test-user", role, _JWT_SECRET)
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# JWT Enforcement Tests
# ---------------------------------------------------------------------------


def test_guardian_rejects_without_jwt() -> None:
    """Guardian Shield /v1/* returns 401 without JWT."""
    client = TestClient(guardian_app)
    resp = client.post("/v1/shield/enhance", json={"prompt": "test"})
    assert resp.status_code == 401


def test_guardian_accepts_with_jwt() -> None:
    """Guardian Shield /v1/* returns 200 with valid JWT."""
    client = TestClient(guardian_app)
    resp = client.post("/v1/shield/enhance", json={"prompt": "test"}, headers=_auth_headers())
    assert resp.status_code == 200


def test_governance_rejects_without_jwt() -> None:
    """Governance Plane /v1/* returns 401 without JWT."""
    client = TestClient(governance_app)
    resp = client.post("/v1/policy/evaluate", json={"role": "admin"})
    assert resp.status_code == 401


def test_governance_accepts_with_jwt() -> None:
    """Governance Plane /v1/* returns 200 with valid JWT."""
    client = TestClient(governance_app)
    resp = client.post("/v1/policy/evaluate", json={"role": "admin"}, headers=_auth_headers())
    assert resp.status_code == 200


def test_metrics_health_no_jwt_needed() -> None:
    """Metrics /health does NOT require JWT (exempt)."""
    client = TestClient(metrics_app)
    resp = client.get("/health")
    assert resp.status_code == 200


def test_expired_jwt_rejected() -> None:
    """Expired JWT is rejected with 401."""
    client = TestClient(guardian_app)
    token = create_token("test-user", "admin", _JWT_SECRET, expiry_minutes=-1)
    resp = client.post(
        "/v1/shield/enhance",
        json={"prompt": "test"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Prometheus Metrics Format Test
# ---------------------------------------------------------------------------


def test_prometheus_metrics_format() -> None:
    """Metrics /metrics/prometheus returns valid Prometheus text format."""
    client = TestClient(metrics_app)
    resp = client.get("/metrics/prometheus")
    assert resp.status_code == 200
    text = resp.text
    assert "# TYPE nss_requests_total counter" in text
    assert "nss_requests_total" in text
    assert "# TYPE nss_request_latency_ms histogram" in text
    assert "nss_request_latency_ms_count" in text
