"""Governance Plane API server (Port 11339).

Exposes policy evaluation, privacy budget, DPIA generation, and
audit trail retrieval as HTTP endpoints.
"""

from __future__ import annotations

from typing import Any

import structlog
import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel

from nss.audit import AuditLogger
from nss.auth import JWTMiddleware
from nss.config import config
from nss.governance.dpia import DPIAGenerator
from nss.governance.policy_engine import PolicyEngine
from nss.governance.privacy_budget import PrivacyBudgetTracker
from nss.middleware import SecurityHeadersMiddleware, TracingMiddleware
from nss.models import DPIAReport, PolicyDecision

logger = structlog.get_logger(__name__)

# -- Request models --


class PolicyRequest(BaseModel):
    role: str = "viewer"
    risk_tier: int | None = None
    pii_detected: bool = False
    privacy_tier: int = 0
    tool_name: str | None = None


class PrivacyConsumeRequest(BaseModel):
    epsilon: float
    user_id: str


class DPIARequest(BaseModel):
    processing_activity: str
    data_categories: list[str]
    risk_tier: int = 3
    privacy_budget_remaining: float = 1.0


# -- Shared instances --

_policy_engine = PolicyEngine()
_privacy_tracker = PrivacyBudgetTracker(
    total_budget=config.privacy_epsilon_budget,
    redis_url=config.redis_url,
)
_dpia_generator = DPIAGenerator()
_audit_logger = AuditLogger(redis_url=config.redis_url)


app = FastAPI(
    title="NSS Governance Plane",
    version="3.1.1",
)

app.add_middleware(TracingMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(JWTMiddleware, secret=config.jwt_secret)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "healthy", "service": "governance-plane"}


@app.post("/v1/policy/evaluate")
async def policy_evaluate(request: PolicyRequest) -> PolicyDecision:
    context = request.model_dump(exclude_none=True)
    result = _policy_engine.evaluate(context)
    _audit_logger.log_event(
        "policy_evaluation",
        user_id=context.get("role", "unknown"),
        layer="governance",
        component="policy_engine",
        details={"allowed": result.allowed, "violations": result.violations},
    )
    return result


@app.get("/v1/privacy/budget/{user_id}")
async def privacy_budget(user_id: str) -> dict[str, Any]:
    remaining = _privacy_tracker.remaining(user_id)
    return {"user_id": user_id, "remaining_epsilon": remaining}


@app.post("/v1/privacy/consume")
async def privacy_consume(request: PrivacyConsumeRequest) -> dict[str, Any]:
    success = _privacy_tracker.consume(request.epsilon, request.user_id)
    remaining = _privacy_tracker.remaining(request.user_id)
    return {
        "success": success,
        "remaining_epsilon": remaining,
        "user_id": request.user_id,
    }


@app.post("/v1/dpia/generate")
async def dpia_generate(request: DPIARequest) -> DPIAReport:
    report = _dpia_generator.generate(
        processing_activity=request.processing_activity,
        data_categories=request.data_categories,
        risk_tier=request.risk_tier,
        privacy_budget_remaining=request.privacy_budget_remaining,
    )
    _audit_logger.log_event(
        "dpia_generated",
        user_id="system",
        layer="governance",
        component="dpia",
        details={"report_id": report.report_id, "risk_level": report.risk_level},
    )
    return report


@app.get("/v1/audit/{audit_id}")
async def audit_trail(audit_id: str) -> list[dict[str, Any]]:
    return _audit_logger.get_trail(audit_id=audit_id)


@app.get("/v1/audit")
async def audit_all() -> dict[str, Any]:
    entries = _audit_logger.get_trail()
    return {"count": len(entries), "entries": entries}


if __name__ == "__main__":
    kwargs: dict[str, Any] = {}
    if config.tls_cert_path and config.tls_key_path:
        kwargs["ssl_certfile"] = config.tls_cert_path
        kwargs["ssl_keyfile"] = config.tls_key_path
    uvicorn.run(
        "nss.governance.server:app",
        host=config.gateway_host,
        port=config.governance_port,
        **kwargs,
    )
