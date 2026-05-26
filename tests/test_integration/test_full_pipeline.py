"""Integration tests: full 6-layer pipeline (happy-path).

Proves that a request can flow through all NSS layers:
PII Redaction -> STEER -> PNC -> SENTINEL -> MARS -> APEX -> SHIELD -> LLM
with audit trail, metrics tracking, and correct latency recording.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from nss.audit import AuditLogger
from nss.gateway.pii_redaction import redact_pii
from nss.gateway.pnc_compression import compress
from nss.gateway.steer import steer_transform
from nss.guardian.mars import MARSScorer, classify_tier
from nss.guardian.sentinel import SentinelDefense
from nss.guardian.shield import APPEND_TOKENS, PREPEND_TOKENS, enhance_prompt
from nss.metrics import Counter, Histogram

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_ollama() -> AsyncMock:
    """Create a fully-mocked OllamaClient."""
    client = AsyncMock()
    client.generate.return_value = "Die Hauptstadt von Österreich ist Wien."
    client.generate_with_confidence.return_value = ("Response text", 0.9)
    client.health_check.return_value = True
    return client


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_pii_then_steer_then_pnc_pipeline() -> None:
    """PII → STEER → PNC produces valid output and metadata."""
    raw = "Contact john@example.com please. Tell me about AI. Tell me about AI."

    # Layer 3a: PII redaction
    redacted, entities = redact_pii(raw)
    assert "john@example.com" not in redacted
    assert "[REDACTED_EMAIL]" in redacted
    assert len(entities) >= 1

    # Layer 3b: STEER transformation
    transformed, steer_meta = steer_transform(redacted, privacy_tier=2)
    assert "Privacy Level: 2" in transformed
    assert steer_meta["privacy_tier"] == 2
    assert steer_meta["language_detected"] in ("de", "en")

    # Layer 3c: PNC compression (duplicate sentence removal)
    compressed, ratio, pnc_meta = compress(transformed)
    assert pnc_meta["compressed_length"] <= pnc_meta["original_length"]


@pytest.mark.asyncio
async def test_sentinel_then_mars_then_apex_pipeline() -> None:
    """SENTINEL → MARS → APEX routing chain with mocked LLM."""
    mock_ollama = _make_mock_ollama()
    # MARS score_risk returns a JSON-like string that gets parsed
    mock_ollama.generate.return_value = (
        '{"score": 0.2, "category": "LOW_RISK", "details": "Safe query."}'
    )

    sentinel = SentinelDefense(mock_ollama, consensus_threshold=2)
    result = await sentinel.check_injection("What is quantum computing?")
    assert result.is_safe is True

    mars = MARSScorer(mock_ollama)
    risk = await mars.score_risk("What is quantum computing?")
    assert 0.0 <= risk.score <= 1.0
    assert risk.tier == classify_tier(risk.score)

    from nss.config import NSSConfig
    from nss.guardian.apex import APEXRouter

    apex = APEXRouter(NSSConfig())
    decision = apex.select_model("What is quantum computing?", result.confidence, 1.0)
    assert decision.model_selected != ""
    assert decision.cost_estimate >= 0.0


def test_shield_wraps_prompt() -> None:
    """SHIELD defensive tokens wrap the user prompt."""
    prompt = "Explain GDPR Article 35."
    enhanced = enhance_prompt(prompt)
    assert PREPEND_TOKENS in enhanced
    assert APPEND_TOKENS in enhanced
    assert prompt in enhanced


def test_audit_trail_tracks_full_request() -> None:
    """Audit logger records events from multiple layers with chain integrity."""
    audit = AuditLogger()

    audit.log_event("pii_redaction", user_id="user-1", layer="gateway", component="pii_redaction",
                    details={"entities_count": 2})
    audit.log_event("sentinel_check", user_id="user-1", layer="guardian", component="sentinel",
                    details={"is_safe": True})
    audit.log_event("mars_scoring", user_id="user-1", layer="guardian", component="mars",
                    details={"score": 0.15, "tier": 3})
    audit.log_event("llm_generation", user_id="user-1", layer="gateway", component="ollama",
                    details={"model": "mistral:7b", "latency_ms": 120})

    trail = audit.get_trail()
    assert len(trail) == 4
    assert trail[0]["event"] == "pii_redaction"
    assert trail[3]["event"] == "llm_generation"

    # Hash-chain integrity
    assert audit.verify_integrity() is True


def test_metrics_accumulate_across_layers() -> None:
    """Counters and histograms track pipeline-wide statistics."""
    req_counter = Counter("test_requests", "Total requests")
    latency_hist = Histogram("test_latency_ms", "Latency")

    req_counter.inc()
    req_counter.inc()
    latency_hist.observe(45.2)
    latency_hist.observe(120.8)

    assert req_counter.value == 2.0
    snap = latency_hist.snapshot()
    assert snap["count"] == 2
    assert snap["min"] == 45.2
    assert snap["max"] == 120.8
    assert 45.0 < snap["avg"] < 121.0
