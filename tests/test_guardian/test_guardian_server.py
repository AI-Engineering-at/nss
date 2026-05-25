"""Tests for Guardian Shield API server."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from nss.auth import create_token
from nss.guardian.server import app

_JWT_SECRET = "change-me-in-production"


def _auth_headers(role: str = "admin") -> dict[str, str]:
    token = create_token("test-user", role, _JWT_SECRET)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def _mock_guardian_components(monkeypatch):
    """Mock all Guardian components to avoid needing Ollama."""
    import nss.guardian.server as srv

    mock_ollama = AsyncMock()
    mock_ollama.generate = AsyncMock(return_value='{"score": 0.15, "category": "LOW", "details": "safe"}')
    mock_ollama.close = AsyncMock()

    mock_mars = AsyncMock()
    mock_mars.score_risk = AsyncMock(return_value=MagicMock(
        score=0.15, tier=3, category="LOW", details="safe",
        model_dump=lambda: {"score": 0.15, "tier": 3, "category": "LOW", "details": "safe"},
    ))

    mock_sentinel = AsyncMock()
    mock_sentinel.check_injection = AsyncMock(return_value=MagicMock(
        is_safe=True, confidence=0.95, method_results={"rules": True, "llm": True, "embedding": True}, consensus="PASS",
        model_dump=lambda: {"is_safe": True, "confidence": 0.95, "method_results": {"rules": True, "llm": True, "embedding": True}, "consensus": "PASS"},
    ))

    from nss.config import NSSConfig
    from nss.guardian.apex import APEXRouter
    mock_apex = APEXRouter(NSSConfig())

    monkeypatch.setattr(srv, "_ollama_client", mock_ollama)
    monkeypatch.setattr(srv, "_mars_scorer", mock_mars)
    monkeypatch.setattr(srv, "_sentinel", mock_sentinel)
    monkeypatch.setattr(srv, "_apex_router", mock_apex)


async def test_health(_mock_guardian_components) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["service"] == "guardian-shield"


async def test_mars_score(_mock_guardian_components) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/v1/mars/score", json={"text": "Hello world"}, headers=_auth_headers())
        assert resp.status_code == 200
        data = resp.json()
        assert "score" in data


async def test_sentinel_check(_mock_guardian_components) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/v1/sentinel/check", json={"text": "normal query"}, headers=_auth_headers())
        assert resp.status_code == 200
        data = resp.json()
        assert "is_safe" in data


async def test_apex_route(_mock_guardian_components) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/v1/apex/route", json={"query": "test", "confidence": 0.9, "budget_remaining": 10.0}, headers=_auth_headers())
        assert resp.status_code == 200
        data = resp.json()
        assert "model_selected" in data


async def test_shield_enhance(_mock_guardian_components) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/v1/shield/enhance", json={"prompt": "Hello"}, headers=_auth_headers())
        assert resp.status_code == 200
        assert "enhanced_prompt" in resp.json()


async def test_vigil_check(_mock_guardian_components) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/v1/vigil/check", json={"tool_name": "search", "args": {"q": "test"}, "user_id": "u1"}, headers=_auth_headers())
        assert resp.status_code == 200
        assert "verdict" in resp.json()
