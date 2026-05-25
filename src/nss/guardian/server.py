"""Guardian Shield API server (Port 11338).

Exposes MARS, SENTINEL, APEX, SHIELD, and VIGIL as HTTP endpoints
for the microservice architecture.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

import structlog
import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel

from nss.auth import JWTMiddleware
from nss.config import config
from nss.guardian.apex import APEXRouter
from nss.guardian.mars import MARSScorer
from nss.guardian.sentinel import SentinelDefense
from nss.guardian.shield import enhance_prompt
from nss.guardian.vigil import check_tool_call
from nss.llm.ollama_client import OllamaClient
from nss.middleware import SecurityHeadersMiddleware, TracingMiddleware
from nss.models import APEXDecision, RiskScore, SentinelResult

logger = structlog.get_logger(__name__)

# -- Request/Response models for API endpoints --


class MARSRequest(BaseModel):
    text: str
    language: str = "de"


class SentinelRequest(BaseModel):
    text: str


class APEXRequest(BaseModel):
    query: str
    confidence: float
    budget_remaining: float


class ShieldRequest(BaseModel):
    prompt: str


class VIGILRequest(BaseModel):
    tool_name: str
    args: dict[str, Any] = {}
    user_id: str


# -- Application --

_ollama_client: OllamaClient | None = None
_mars_scorer: MARSScorer | None = None
_sentinel: SentinelDefense | None = None
_apex_router: APEXRouter | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _ollama_client, _mars_scorer, _sentinel, _apex_router
    _ollama_client = OllamaClient(
        base_url=config.ollama_base_url,
        default_model=config.ollama_small_model,
    )
    _mars_scorer = MARSScorer(_ollama_client)
    _sentinel = SentinelDefense(
        _ollama_client,
        consensus_threshold=config.sentinel_consensus_threshold,
    )
    _apex_router = APEXRouter(config)
    logger.info("guardian_shield_started", port=config.guardian_port)
    yield
    if _ollama_client:
        await _ollama_client.close()
    logger.info("guardian_shield_stopped")


app = FastAPI(
    title="NSS Guardian Shield",
    version="3.1.1",
    lifespan=lifespan,
)

app.add_middleware(TracingMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(JWTMiddleware, secret=config.jwt_secret)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "healthy", "service": "guardian-shield"}


@app.post("/v1/mars/score")
async def mars_score(request: MARSRequest) -> RiskScore:
    assert _mars_scorer is not None
    return await _mars_scorer.score_risk(request.text, request.language)


@app.post("/v1/sentinel/check")
async def sentinel_check(request: SentinelRequest) -> SentinelResult:
    assert _sentinel is not None
    return await _sentinel.check_injection(request.text)


@app.post("/v1/apex/route")
async def apex_route(request: APEXRequest) -> APEXDecision:
    assert _apex_router is not None
    return _apex_router.select_model(
        request.query, request.confidence, request.budget_remaining,
    )


@app.post("/v1/shield/enhance")
async def shield_enhance(request: ShieldRequest) -> dict[str, str]:
    result = enhance_prompt(request.prompt)
    return {"enhanced_prompt": result}


@app.post("/v1/vigil/check")
async def vigil_check(request: VIGILRequest) -> dict[str, Any]:
    return check_tool_call(request.tool_name, request.args, request.user_id)


if __name__ == "__main__":
    kwargs: dict[str, Any] = {}
    if config.tls_cert_path and config.tls_key_path:
        kwargs["ssl_certfile"] = config.tls_cert_path
        kwargs["ssl_keyfile"] = config.tls_key_path
    uvicorn.run(
        "nss.guardian.server:app",
        host=config.gateway_host,
        port=config.guardian_port,
        **kwargs,
    )
