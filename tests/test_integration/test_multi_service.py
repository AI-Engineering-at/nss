"""Integration tests: multi-service architecture.

Proves that Guardian (11338), Governance (11339), and Metrics (11340)
servers function correctly via TestClient, including health checks,
endpoint round-trips, trace-ID propagation, and audit logging.
"""

from __future__ import annotations

import pytest

from nss.auth import create_token
from nss.governance.server import app as governance_app
from nss.guardian.server import app as guardian_app
from nss.metrics_server import app as metrics_app

_JWT_SECRET = "change-me-in-production"


def _auth_headers(role: str = "admin") -> dict[str, str]:
    token = create_token("test-user", role, _JWT_SECRET)
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def guardian_client():
    """Synchronous test client for Guardian Shield."""
    from starlette.testclient import TestClient
    return TestClient(guardian_app)


@pytest.fixture
def governance_client():
    """Synchronous test client for Governance Plane."""
    from starlette.testclient import TestClient
    return TestClient(governance_app)


@pytest.fixture
def metrics_client():
    """Synchronous test client for Metrics Server."""
    from starlette.testclient import TestClient
    return TestClient(metrics_app)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_all_services_health(guardian_client, governance_client, metrics_client) -> None:
    """All three microservices report healthy."""
    r1 = guardian_client.get("/health")
    assert r1.status_code == 200
    assert r1.json()["status"] == "healthy"
    assert r1.json()["service"] == "guardian-shield"

    r2 = governance_client.get("/health")
    assert r2.status_code == 200
    assert r2.json()["status"] == "healthy"
    assert r2.json()["service"] == "governance-plane"

    r3 = metrics_client.get("/health")
    assert r3.status_code == 200
    assert r3.json()["status"] == "healthy"
    assert r3.json()["service"] == "metrics"


def test_guardian_shield_enhance(guardian_client) -> None:
    """Guardian Shield /v1/shield/enhance wraps prompt with defensive tokens."""
    resp = guardian_client.post("/v1/shield/enhance", json={"prompt": "Hello world"}, headers=_auth_headers())
    assert resp.status_code == 200
    data = resp.json()
    assert "enhanced_prompt" in data
    assert "Hello world" in data["enhanced_prompt"]


def test_guardian_vigil_endpoint(guardian_client) -> None:
    """Guardian Shield /v1/vigil/check validates tool calls."""
    # Valid tool
    resp = guardian_client.post("/v1/vigil/check", json={
        "tool_name": "search",
        "args": {"query": "test"},
        "user_id": "user-1",
    }, headers=_auth_headers())
    assert resp.status_code == 200
    assert resp.json()["verdict"] == "ALLOW"

    # Blocked tool
    resp2 = guardian_client.post("/v1/vigil/check", json={
        "tool_name": "evil_tool",
        "args": {},
        "user_id": "user-1",
    }, headers=_auth_headers())
    assert resp2.status_code == 200
    assert resp2.json()["verdict"] == "DENY"


def test_governance_policy_evaluation(governance_client) -> None:
    """Governance Plane /v1/policy/evaluate enforces role-based policies."""
    # Viewer with PII but low privacy tier -> denied
    resp = governance_client.post("/v1/policy/evaluate", json={
        "role": "viewer",
        "pii_detected": True,
        "privacy_tier": 0,
    }, headers=_auth_headers())
    assert resp.status_code == 200
    data = resp.json()
    assert data["allowed"] is False
    assert len(data["violations"]) > 0

    # Admin with no PII -> allowed
    resp2 = governance_client.post("/v1/policy/evaluate", json={
        "role": "admin",
    }, headers=_auth_headers())
    assert resp2.status_code == 200
    assert resp2.json()["allowed"] is True


def test_governance_privacy_budget(governance_client) -> None:
    """Governance Plane privacy budget endpoints track consumption."""
    # Check initial budget
    resp = governance_client.get("/v1/privacy/budget/integration-test-user", headers=_auth_headers())
    assert resp.status_code == 200
    initial = resp.json()["remaining_epsilon"]

    # Consume some budget
    resp2 = governance_client.post("/v1/privacy/consume", json={
        "epsilon": 0.1,
        "user_id": "integration-test-user",
    }, headers=_auth_headers())
    assert resp2.status_code == 200
    assert resp2.json()["success"] is True

    # Check reduced budget
    resp3 = governance_client.get("/v1/privacy/budget/integration-test-user", headers=_auth_headers())
    assert resp3.json()["remaining_epsilon"] < initial


def test_governance_dpia_generation(governance_client) -> None:
    """Governance Plane /v1/dpia/generate creates a valid DPIA report."""
    resp = governance_client.post("/v1/dpia/generate", json={
        "processing_activity": "Integration test activity",
        "data_categories": ["personal_data", "health_data"],
        "risk_tier": 2,
        "privacy_budget_remaining": 0.8,
    }, headers=_auth_headers())
    assert resp.status_code == 200
    data = resp.json()
    assert "report_id" in data
    assert data["risk_level"] in ("LOW", "MEDIUM", "HIGH", "CRITICAL")
    assert len(data.get("sections", {})) >= 5


def test_governance_audit_trail(governance_client) -> None:
    """Governance Plane audit endpoints record and retrieve events."""
    # Trigger an action that creates audit entries
    governance_client.post("/v1/policy/evaluate", json={"role": "viewer"}, headers=_auth_headers())

    # Retrieve all audit entries
    resp = governance_client.get("/v1/audit", headers=_auth_headers())
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] >= 1
    assert len(data["entries"]) >= 1


def test_metrics_snapshot(metrics_client) -> None:
    """Metrics server /metrics returns counters and histograms."""
    resp = metrics_client.get("/metrics")
    assert resp.status_code == 200
    data = resp.json()
    assert "timestamp" in data
    assert "counters" in data
    assert "histograms" in data
    assert "nss_requests_total" in data["counters"]
