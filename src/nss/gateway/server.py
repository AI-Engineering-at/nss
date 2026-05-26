"""Cognitive Gateway -- FastAPI application serving the NSS processing pipeline.

Binds to 127.0.0.1 only (no external exposure by default).
Pipeline: HMAC verify -> JWT auth -> Policy pre-check -> PII redaction ->
          STEER transform -> PNC compression -> SENTINEL check -> MARS scoring ->
          Policy post-check -> APEX routing -> SHIELD enhancement ->
          LLM generation (with cache) -> Privacy budget consume.
"""

from __future__ import annotations

import asyncio
import hashlib
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import structlog
import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from nss import __version__
from nss.agent.tool_isolation import ToolSandbox
from nss.audit import AuditLogger
from nss.auth import JWTMiddleware
from nss.cache import CacheLayer
from nss.config import config
from nss.gateway.hmac_signing import verify_request
from nss.gateway.pii_redaction import redact_pii
from nss.gateway.pnc_compression import compress
from nss.gateway.steer import steer_transform
from nss.governance.dpia import DPIAGenerator
from nss.governance.policy_engine import PolicyEngine
from nss.governance.privacy_budget import PrivacyBudgetTracker
from nss.guardian.apex import APEXRouter
from nss.guardian.mars import MARSScorer
from nss.guardian.sentinel import SentinelDefense
from nss.guardian.shield import enhance_prompt
from nss.llm.ollama_client import OllamaClient
from nss.metrics import (
    metrics_snapshot,
    nss_guardian_latency,
    nss_pii_entities_redacted,
    nss_privacy_budget_consumed,
    nss_request_latency,
    nss_requests_blocked,
    nss_requests_total,
)
from nss.middleware import (
    RateLimitMiddleware,
    SecurityHeadersMiddleware,
    TracingMiddleware,
)
from nss.models import NSSRequest, NSSResponse

logger = structlog.get_logger(__name__)

# -- Shared state (populated during lifespan) --------------------------------
_ollama_client: OllamaClient | None = None
_mars_scorer: MARSScorer | None = None
_apex_router: APEXRouter | None = None
_sentinel: SentinelDefense | None = None
_audit_logger: AuditLogger | None = None
_cache: CacheLayer | None = None
_policy_engine: PolicyEngine | None = None
_privacy_budget: PrivacyBudgetTracker | None = None
_tool_sandbox: ToolSandbox | None = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup / shutdown hook for the gateway."""
    global _ollama_client, _mars_scorer, _apex_router, _sentinel
    global _audit_logger, _cache, _policy_engine, _privacy_budget, _tool_sandbox

    logger.info("gateway_starting", version=__version__, port=config.gateway_port)

    _ollama_client = OllamaClient(
        base_url=config.ollama_base_url,
        default_model=config.ollama_small_model,
    )
    _mars_scorer = MARSScorer(ollama_client=_ollama_client)
    _apex_router = APEXRouter(config=config)
    _sentinel = SentinelDefense(
        ollama_client=_ollama_client,
        consensus_threshold=config.sentinel_consensus_threshold,
    )
    _audit_logger = AuditLogger(redis_url=config.redis_url)
    _policy_engine = PolicyEngine()
    _privacy_budget = PrivacyBudgetTracker(
        total_budget=config.privacy_epsilon_budget,
        redis_url=config.redis_url,
    )
    _tool_sandbox = ToolSandbox()

    # Cache layer (graceful -- works without Redis)
    _cache = CacheLayer(redis_url=config.redis_url)
    try:
        await _cache.connect()
        logger.info("cache_connected", redis_url=config.redis_url)
    except Exception:
        logger.warning("cache_unavailable", redis_url=config.redis_url)

    logger.info("gateway_ready")
    yield

    # Shutdown
    if _cache is not None:
        await _cache.close()
    if _ollama_client is not None:
        await _ollama_client.close()
    logger.info("gateway_stopped")


app = FastAPI(
    title="NSS Cognitive Gateway",
    version=__version__,
    lifespan=lifespan,
)

# -- Middleware (LIFO order: first added = innermost) -------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1"],
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)
app.add_middleware(RateLimitMiddleware, max_requests=config.rate_limit_rpm, window_seconds=60)
app.add_middleware(TracingMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(JWTMiddleware, secret=config.jwt_secret)


# -- Middleware: request logging ---------------------------------------------
@app.middleware("http")
async def log_requests(request: Request, call_next):  # type: ignore[no-untyped-def]
    """Log every inbound request with timing information."""
    start = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - start) * 1000
    logger.info(
        "http_request",
        method=request.method,
        path=request.url.path,
        status=response.status_code,
        latency_ms=round(elapsed_ms, 2),
    )
    return response


# -- HMAC Verification Dependency --------------------------------------------


async def verify_hmac(request: Request) -> NSSRequest:
    """FastAPI dependency: verify HMAC signature on request body."""
    body = await request.body()
    sig = request.headers.get("X-HMAC-Signature", "")
    ts = request.headers.get("X-HMAC-Timestamp", "")
    nonce = request.headers.get("X-HMAC-Nonce", "")

    if not verify_request(body.decode(), sig, config.hmac_secret, ts, nonce):
        raise HTTPException(status_code=401, detail="Invalid HMAC signature.")

    return NSSRequest.model_validate_json(body)


# -- Endpoints ---------------------------------------------------------------


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness / readiness probe."""
    return {"status": "healthy", "version": __version__}


@app.get("/metrics")
async def metrics() -> dict[str, Any]:
    """Return operational metrics from the metrics registry."""
    return metrics_snapshot()


@app.post("/v1/process", response_model=NSSResponse)
async def process(
    request: Request,
    nss_request: NSSRequest = Depends(verify_hmac),
) -> NSSResponse:
    """Run the full NSS processing pipeline on an inbound request.

    Steps:
        0a. HMAC verification (via dependency)
        0b. JWT authentication (via middleware)
        0c. Policy pre-check (role + privacy_tier)
        0d. Privacy budget check
        1. PII redaction
        2. STEER transformation (language detection, privacy-tier context)
        3. PNC compression (deduplication, filler removal, token budget)
        4. SENTINEL injection check
        5. MARS risk scoring
        5b. Policy post-check (role + risk_tier + pii)
        6. APEX model routing
        7. SHIELD prompt enhancement
        8. LLM generation (with cache)
        9. Privacy budget consumption
    """
    assert _ollama_client is not None
    assert _mars_scorer is not None
    assert _apex_router is not None
    assert _sentinel is not None
    assert _audit_logger is not None
    assert _policy_engine is not None
    assert _privacy_budget is not None

    start = time.perf_counter()
    audit_id = str(uuid.uuid4())
    nss_requests_total.inc()

    # Extract role from JWT (set by JWTMiddleware)
    role = getattr(request.state, "role", "viewer")
    user_id = nss_request.user_id

    # 0c. Policy pre-check (role + privacy_tier)
    pre_decision = _policy_engine.evaluate({
        "role": role,
        "privacy_tier": nss_request.privacy_tier,
    })
    if not pre_decision.allowed:
        nss_requests_blocked.inc()
        raise HTTPException(status_code=403, detail=pre_decision.violations)

    # 0d. Privacy budget check
    remaining = _privacy_budget.remaining(user_id)
    if remaining <= 0:
        raise HTTPException(
            status_code=429,
            detail="Privacy budget exhausted for this user.",
        )

    # 1. PII Redaction
    redacted_message, entities = redact_pii(nss_request.message)
    if entities:
        nss_pii_entities_redacted.inc(len(entities))
        logger.info("pii_redacted", audit_id=audit_id, count=len(entities))
    _audit_logger.log_event(
        "pii_redaction",
        user_id=user_id,
        layer="gateway",
        component="pii_redaction",
        details={"entities_count": len(entities), "audit_id": audit_id},
    )

    # 2. STEER Transformation
    transformed_message, steer_meta = steer_transform(
        redacted_message, privacy_tier=nss_request.privacy_tier,
    )

    # 3. PNC Compression
    compressed_message, compression_ratio, pnc_meta = compress(transformed_message)

    # 4. SENTINEL injection check
    guardian_start = time.perf_counter()
    sentinel_result = await _sentinel.check_injection(compressed_message)
    _audit_logger.log_event(
        "sentinel_check",
        user_id=user_id,
        layer="guardian",
        component="sentinel",
        details={
            "is_safe": sentinel_result.is_safe,
            "confidence": sentinel_result.confidence,
            "audit_id": audit_id,
        },
    )
    if not sentinel_result.is_safe:
        nss_requests_blocked.inc()
        raise HTTPException(
            status_code=422,
            detail=f"Request blocked by SENTINEL: {sentinel_result.consensus}",
        )

    # 5. MARS risk scoring
    risk = await _mars_scorer.score_risk(compressed_message)
    _audit_logger.log_event(
        "mars_scoring",
        user_id=user_id,
        layer="guardian",
        component="mars",
        details={"score": risk.score, "tier": risk.tier, "audit_id": audit_id},
    )

    # 5b. Policy post-check (with risk_tier and pii_detected)
    full_decision = _policy_engine.evaluate({
        "role": role,
        "risk_tier": risk.tier,
        "pii_detected": bool(entities),
        "privacy_tier": nss_request.privacy_tier,
    })
    if not full_decision.allowed:
        nss_requests_blocked.inc()
        raise HTTPException(status_code=403, detail=full_decision.violations)

    # 5c. DPIA auto-trigger for high-risk requests (fire-and-forget)
    if risk.tier <= 1:
        asyncio.create_task(_fire_dpia(user_id, risk, entities, audit_id))

    # 6. APEX model routing
    decision = _apex_router.select_model(
        query=compressed_message,
        confidence=sentinel_result.confidence,
        budget_remaining=1.0,
    )

    guardian_elapsed_ms = (time.perf_counter() - guardian_start) * 1000
    nss_guardian_latency.observe(guardian_elapsed_ms)

    # 7. SHIELD prompt enhancement
    safe_prompt = enhance_prompt(compressed_message)

    # 8. LLM generation (with cache)
    cache_key = hashlib.sha256(
        f"{safe_prompt}:{decision.model_selected}".encode(),
    ).hexdigest()

    response_text = None
    if _cache is not None:
        try:
            response_text = await _cache.get("gateway", cache_key)
        except Exception:
            pass  # graceful degradation

    if response_text is None:
        response_text = await _ollama_client.generate(
            prompt=safe_prompt,
            model=decision.model_selected,
        )
        if _cache is not None:
            try:
                await _cache.set("gateway", cache_key, response_text)
            except Exception:
                pass  # graceful degradation

    _audit_logger.log_event(
        "llm_generation",
        user_id=user_id,
        layer="gateway",
        component="ollama",
        details={
            "model": decision.model_selected,
            "audit_id": audit_id,
            "cache_hit": response_text is not None,
        },
    )

    # 9. Privacy budget consumption
    _privacy_budget.consume(config.privacy_epsilon_per_query, user_id)
    nss_privacy_budget_consumed.inc(config.privacy_epsilon_per_query)

    elapsed_ms = (time.perf_counter() - start) * 1000
    nss_request_latency.observe(elapsed_ms)

    return NSSResponse(
        response=response_text,
        risk_score=risk.score,
        model_used=decision.model_selected,
        latency_ms=round(elapsed_ms, 2),
        privacy_tier=nss_request.privacy_tier,
        audit_id=audit_id,
    )


# -- Tool Execution Endpoint -------------------------------------------------


class ToolExecRequest(BaseModel):
    """Request body for tool execution."""
    tool_name: str
    args: dict[str, Any] = {}
    user_id: str
    timeout: float | None = None


@app.post("/v1/tools/execute")
async def tool_execute(request: Request, body: ToolExecRequest) -> dict[str, Any]:
    """Execute a registered tool in the WASM/WASI sandbox.

    The tool is validated by VIGIL before execution and subject to
    timeout enforcement via process isolation.
    """
    assert _tool_sandbox is not None
    assert _audit_logger is not None

    result = _tool_sandbox.execute_tool(
        tool_name=body.tool_name,
        args=body.args,
        user_id=body.user_id,
        timeout=body.timeout,
    )

    _audit_logger.log_event(
        "tool_execution",
        user_id=body.user_id,
        layer="agent",
        component="tool_sandbox",
        details={
            "tool": body.tool_name,
            "vigil_verdict": result.vigil_verdict,
            "execution_time_ms": result.execution_time_ms,
        },
    )

    return {
        "output": result.output,
        "vigil_verdict": result.vigil_verdict,
        "execution_time_ms": result.execution_time_ms,
        "sandbox_metadata": result.sandbox_metadata,
    }


# -- DPIA Auto-Trigger (fire-and-forget) -------------------------------------


async def _fire_dpia(
    user_id: str,
    risk: Any,
    entities: list[Any],
    audit_id: str,
) -> None:
    """Auto-generate DPIA for high-risk requests (risk_tier <= 1)."""
    try:
        dpia_gen = DPIAGenerator()
        entity_types = [str(e) for e in entities] if entities else []
        report = dpia_gen.generate(
            processing_activity=f"High-risk query from user {user_id}",
            data_categories=["user_query"] + entity_types,
            risk_tier=risk.tier,
            privacy_budget_remaining=(
                _privacy_budget.remaining(user_id) if _privacy_budget else 1.0
            ),
        )
        if _audit_logger:
            _audit_logger.log_event(
                "dpia_auto_generated",
                user_id=user_id,
                layer="governance",
                component="dpia",
                details={
                    "report_id": report.report_id,
                    "risk_level": report.risk_level,
                    "audit_id": audit_id,
                },
            )
        logger.info("dpia_auto_generated", report_id=report.report_id)
    except Exception:
        logger.warning("dpia_auto_trigger_failed", user_id=user_id)


# -- Unlearning Endpoint (GDPR Art. 17) --------------------------------------


@app.post("/v1/unlearn/{user_id}")
async def unlearn_user(user_id: str) -> dict[str, Any]:
    """GDPR Art. 17: Right to be forgotten -- orchestrate data deletion."""
    results: dict[str, Any] = {}

    # Reset privacy budget
    if _privacy_budget is not None:
        _privacy_budget.reset(user_id)
        results["budget_reset"] = True

    # Cache entries expire naturally (300s TTL)
    results["cache_note"] = "Cache entries expire within 5 minutes (TTL=300s)"

    # Vector store deletion (best-effort -- Qdrant may not be running)
    try:
        from nss.knowledge.vector_store import VectorStore

        vs = VectorStore(host=config.qdrant_host, port=config.qdrant_port)
        await vs.delete_by_user(user_id)
        results["vectors_deleted"] = True
    except Exception:
        results["vectors_deleted"] = False
        logger.warning("unlearn_vector_delete_failed", user_id=user_id)

    # Log the unlearning event
    if _audit_logger is not None:
        _audit_logger.log_event(
            "user_unlearning",
            user_id=user_id,
            layer="gateway",
            component="unlearning_orchestrator",
            details={"actions": results},
        )

    return {"user_id": user_id, "actions": results}


# -- Entrypoint --------------------------------------------------------------


def main() -> None:
    """Launch the Cognitive Gateway via uvicorn."""
    kwargs: dict[str, Any] = {}
    if config.tls_cert_path and config.tls_key_path:
        kwargs["ssl_certfile"] = config.tls_cert_path
        kwargs["ssl_keyfile"] = config.tls_key_path
    uvicorn.run(
        "nss.gateway.server:app",
        host=config.gateway_host,
        port=config.gateway_port,
        log_level=config.log_level.lower(),
        **kwargs,
    )


if __name__ == "__main__":
    main()
