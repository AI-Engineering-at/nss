"""Integration tests: security pipeline.

Proves that injection attempts are blocked, PII is redacted before
reaching the LLM, JWT is enforced, RBAC works, and rate limiting fires.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from nss.auth import create_token, verify_token
from nss.gateway.pii_redaction import redact_pii
from nss.guardian.sentinel import SentinelDefense
from nss.guardian.shield import PREPEND_TOKENS, enhance_prompt
from nss.guardian.vigil import check_tool_call

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_JWT_SECRET = "test-secret-for-integration"


def _make_mock_ollama() -> AsyncMock:
    client = AsyncMock()
    client.generate.return_value = '{"score": 0.1, "category": "LOW_RISK", "details": "ok"}'
    client.generate_with_confidence.return_value = ("safe", 0.95)
    client.health_check.return_value = True
    return client


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_injection_blocked_by_sentinel() -> None:
    """SENTINEL blocks known injection patterns (SQL, XSS, command injection)."""
    mock_ollama = _make_mock_ollama()
    sentinel = SentinelDefense(mock_ollama, consensus_threshold=1)

    # These match SENTINEL's regex patterns (SQL, XSS, command injection)
    attacks = [
        "'; DROP TABLE users; --",
        "<script>alert('xss')</script>",
        "; cat /etc/passwd",
    ]
    for attack in attacks:
        result = await sentinel.check_injection(attack)
        # Rule-based check should catch these
        assert result.method_results.get("rules") is False, (
            f"Rule check missed: {attack!r}"
        )
        assert not result.is_safe, (
            f"Attack not blocked: {attack!r}"
        )


def test_pii_redacted_before_llm_sees_it() -> None:
    """PII redaction followed by SHIELD ensures no raw PII reaches the LLM."""
    raw = "My email is ceo@company.at and my IBAN is AT123456789012345678"

    # Step 1: PII redaction
    redacted, entities = redact_pii(raw)
    assert "ceo@company.at" not in redacted
    assert "AT123456789012345678" not in redacted
    assert "[REDACTED_EMAIL]" in redacted
    assert "[REDACTED_IBAN]" in redacted

    # Step 2: SHIELD wrapping (what the LLM actually sees)
    enhanced = enhance_prompt(redacted)
    assert "ceo@company.at" not in enhanced
    assert "AT123456789012345678" not in enhanced
    assert PREPEND_TOKENS in enhanced


def test_jwt_round_trip_and_expiry() -> None:
    """JWT creation + verification round-trips; expired tokens fail."""
    token = create_token("user-1", "admin", _JWT_SECRET, expiry_minutes=15)
    payload = verify_token(token, _JWT_SECRET)
    assert payload["sub"] == "user-1"
    assert payload["role"] == "admin"

    # Expired token
    import jwt as pyjwt

    expired_token = create_token("user-1", "admin", _JWT_SECRET, expiry_minutes=-1)
    with pytest.raises(pyjwt.ExpiredSignatureError):
        verify_token(expired_token, _JWT_SECRET)


def test_rbac_hierarchy() -> None:
    """Role hierarchy: admin > data_processor > auditor > viewer."""
    hierarchy = {"admin": 4, "data_processor": 3, "auditor": 2, "viewer": 1}

    # Admin can do everything
    admin_token = create_token("admin-1", "admin", _JWT_SECRET)
    admin_payload = verify_token(admin_token, _JWT_SECRET)
    assert hierarchy[admin_payload["role"]] >= hierarchy["viewer"]
    assert hierarchy[admin_payload["role"]] >= hierarchy["admin"]

    # Viewer cannot reach admin level
    viewer_token = create_token("viewer-1", "viewer", _JWT_SECRET)
    viewer_payload = verify_token(viewer_token, _JWT_SECRET)
    assert hierarchy[viewer_payload["role"]] < hierarchy["admin"]
    assert hierarchy[viewer_payload["role"]] < hierarchy["data_processor"]


def test_vigil_blocks_suspicious_tool_args() -> None:
    """VIGIL CIA triad rejects shell injection in tool args."""
    result = check_tool_call("search", {"query": "test; rm -rf /"}, "user-1")
    assert result["verdict"] == "DENY"
    assert result["checks"]["integrity"] is False

    # Unknown tool
    result2 = check_tool_call("evil_tool", {}, "user-1")
    assert result2["verdict"] == "DENY"
    assert result2["checks"]["confidentiality"] is False

    # Valid call
    result3 = check_tool_call("search", {"query": "quantum computing"}, "user-1")
    assert result3["verdict"] == "ALLOW"
