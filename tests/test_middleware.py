"""Tests for HTTP middleware (security headers, tracing, rate limiting)."""

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from nss.middleware import RateLimitMiddleware, SecurityHeadersMiddleware, TracingMiddleware


def _make_app(max_requests: int = 5) -> FastAPI:
    """Create a minimal FastAPI app with all middleware."""
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware, max_requests=max_requests, window_seconds=60)
    app.add_middleware(TracingMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)

    @app.get("/test")
    async def test_endpoint():
        return {"ok": True}

    @app.get("/health")
    async def health():
        return "healthy"

    return app


@pytest.fixture
def app():
    return _make_app()


async def test_security_headers_present(app: FastAPI) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/test")
        assert resp.headers["X-Content-Type-Options"] == "nosniff"
        assert resp.headers["X-Frame-Options"] == "DENY"
        assert "Strict-Transport-Security" in resp.headers


async def test_trace_id_generated(app: FastAPI) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/test")
        assert "X-Trace-ID" in resp.headers
        assert len(resp.headers["X-Trace-ID"]) == 36  # UUID


async def test_trace_id_propagated(app: FastAPI) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/test", headers={"X-Trace-ID": "my-custom-trace"})
        assert resp.headers["X-Trace-ID"] == "my-custom-trace"


async def test_rate_limit_enforced() -> None:
    app = _make_app(max_requests=3)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for _ in range(3):
            resp = await client.get("/test")
            assert resp.status_code == 200
        resp = await client.get("/test")
        assert resp.status_code == 429
