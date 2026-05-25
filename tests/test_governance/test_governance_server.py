"""Tests for Governance Plane API server."""

from httpx import ASGITransport, AsyncClient

from nss.auth import create_token
from nss.governance.server import app

_JWT_SECRET = "change-me-in-production"


def _auth_headers(role: str = "admin") -> dict[str, str]:
    token = create_token("test-user", role, _JWT_SECRET)
    return {"Authorization": f"Bearer {token}"}


async def test_health() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["service"] == "governance-plane"


async def test_policy_evaluate() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/v1/policy/evaluate", json={"role": "admin"}, headers=_auth_headers())
        assert resp.status_code == 200
        data = resp.json()
        assert data["allowed"] is True


async def test_privacy_budget() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/v1/privacy/budget/user-1", headers=_auth_headers())
        assert resp.status_code == 200
        data = resp.json()
        assert "remaining_epsilon" in data


async def test_dpia_generate() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/v1/dpia/generate", json={
            "processing_activity": "LLM query",
            "data_categories": ["email"],
            "risk_tier": 2,
        }, headers=_auth_headers())
        assert resp.status_code == 200
        data = resp.json()
        assert "report_id" in data
        assert "sections" in data


async def test_audit_trail() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # First create an audit event via policy evaluation
        await client.post("/v1/policy/evaluate", json={"role": "viewer"}, headers=_auth_headers())
        # Then retrieve all audit entries
        resp = await client.get("/v1/audit", headers=_auth_headers())
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] >= 1
