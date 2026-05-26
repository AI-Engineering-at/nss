"""Tests for the Unlearning Orchestrator (GDPR Art. 17) endpoint."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from nss.auth import create_token

_JWT_SECRET = "change-me-in-production"


def _auth_headers() -> dict[str, str]:
    token = create_token("admin-user", "admin", _JWT_SECRET)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def anyio_backend():
    return "asyncio"


class TestUnlearningEndpoint:
    """Tests for /v1/unlearn/{user_id}."""

    async def test_unlearn_resets_budget(self):
        """Unlearn endpoint resets the user's privacy budget."""
        from nss.gateway import server as gw
        from nss.governance.privacy_budget import PrivacyBudgetTracker

        # Ensure privacy budget is initialised for this test
        if gw._privacy_budget is None:
            gw._privacy_budget = PrivacyBudgetTracker(total_budget=1.0)

        # Consume some budget first
        gw._privacy_budget.consume(0.3, "user42")
        assert gw._privacy_budget.remaining("user42") < 1.0

        async with AsyncClient(
            transport=ASGITransport(app=gw.app),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/v1/unlearn/user42",
                headers=_auth_headers(),
            )
        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == "user42"
        assert data["actions"]["budget_reset"] is True
        # Budget should be reset to full
        assert gw._privacy_budget.remaining("user42") == 1.0

    async def test_unlearn_logs_audit_event(self):
        """Unlearn endpoint creates an audit trail entry."""
        from nss.gateway.server import _audit_logger, app

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            await client.post(
                "/v1/unlearn/audit_test_user",
                headers=_auth_headers(),
            )

        # Check audit trail for unlearning event
        if _audit_logger is not None:
            trail = _audit_logger.get_trail()
            unlearn_events = [
                e for e in trail
                if e["event"] == "user_unlearning"
                and e["user_id"] == "audit_test_user"
            ]
            assert len(unlearn_events) >= 1

    async def test_unlearn_requires_jwt(self):
        """Unlearn endpoint requires JWT authentication."""
        from nss.gateway.server import app

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post("/v1/unlearn/user42")
        assert response.status_code == 401
