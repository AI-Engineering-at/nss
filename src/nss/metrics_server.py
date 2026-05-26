"""Metrics API server (Port 11340).

Lightweight server exposing NSS operational metrics.
"""

from __future__ import annotations

from typing import Any

import uvicorn
from fastapi import FastAPI
from starlette.responses import PlainTextResponse

from nss.auth import JWTMiddleware
from nss.config import config
from nss.metrics import metrics_snapshot, prometheus_export
from nss.middleware import SecurityHeadersMiddleware, TracingMiddleware

app = FastAPI(
    title="NSS Metrics",
    version="3.1.1",
)

app.add_middleware(TracingMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(JWTMiddleware, secret=config.jwt_secret)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "healthy", "service": "metrics"}


@app.get("/metrics")
async def metrics() -> dict[str, Any]:
    return metrics_snapshot()


@app.get("/metrics/prometheus")
async def metrics_prometheus() -> PlainTextResponse:
    return PlainTextResponse(prometheus_export(), media_type="text/plain; version=0.0.4")


if __name__ == "__main__":
    # TLS kwargs are passed through unchanged to uvicorn.run.
    # `Any` is correct here because uvicorn.run accepts heterogeneous kwargs
    # (str paths for SSL files vs. mixed-type config); declaring `dict[str, str]`
    # caused 11 false-positive arg-type errors against uvicorn's untyped **kwargs.
    kwargs: dict[str, Any] = {}
    if config.tls_cert_path and config.tls_key_path:
        kwargs["ssl_certfile"] = config.tls_cert_path
        kwargs["ssl_keyfile"] = config.tls_key_path
    uvicorn.run(
        "nss.metrics_server:app",
        host=config.gateway_host,
        port=config.metrics_port,
        **kwargs,
    )
