"""Integration tests: privacy pipeline.

Proves differential privacy (dpsparsevote_rag), epsilon budget tracking,
DPIA generation, and privacy-tier enforcement work end-to-end.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from nss.agent.dp_sparse_vote import add_dp_noise, dpsparsevote_rag
from nss.gateway.steer import steer_transform
from nss.governance.dpia import DPIAGenerator
from nss.governance.policy_engine import PolicyEngine
from nss.governance.privacy_budget import PrivacyBudgetTracker

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_deps():
    """Create mocked ollama_client and vector_store."""
    ollama = AsyncMock()
    ollama.generate.return_value = "Generated answer about topic."
    ollama.generate_with_confidence.return_value = ("Generated answer", 0.85)

    vector_store = AsyncMock()
    vector_store.search.return_value = [
        {"id": "doc-1", "score": 0.92, "payload": {"text": "Relevant document.", "user_id": "u1"}},
        {"id": "doc-2", "score": 0.88, "payload": {"text": "Another document.", "user_id": "u1"}},
        {"id": "doc-3", "score": 0.85, "payload": {"text": "Third document.", "user_id": "u1"}},
    ]

    return ollama, vector_store


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dp_sparse_vote_with_budget() -> None:
    """dpsparsevote_rag queries with noise and consumes epsilon budget."""
    ollama, vector_store = _make_mock_deps()
    budget = PrivacyBudgetTracker(total_budget=1.0)

    with patch("nss.knowledge.embeddings.EmbeddingService") as mock_embed_cls:
        mock_embed_cls.return_value.embed.return_value = [0.1] * 384

        result = await dpsparsevote_rag(
            query="What is sovereign AI?",
            vector_store=vector_store,
            ollama_client=ollama,
            privacy_budget=budget,
            user_id="user-1",
            top_k=3,
            epsilon_per_query=0.1,
        )

    assert isinstance(result, str)
    assert len(result) > 0
    assert budget.remaining("user-1") < 1.0


@pytest.mark.asyncio
async def test_dp_budget_exhaustion() -> None:
    """Privacy budget exhaustion returns error message."""
    ollama, vector_store = _make_mock_deps()
    budget = PrivacyBudgetTracker(total_budget=0.15)

    with patch("nss.knowledge.embeddings.EmbeddingService") as mock_embed_cls:
        mock_embed_cls.return_value.embed.return_value = [0.1] * 384

        # First query consumes 0.1 → 0.05 remaining
        r1 = await dpsparsevote_rag(
            query="Q1", vector_store=vector_store, ollama_client=ollama,
            privacy_budget=budget, user_id="budget-user", epsilon_per_query=0.1,
        )
        assert len(r1) > 0

        # Second query tries 0.1 but only 0.05 left → denied
        r2 = await dpsparsevote_rag(
            query="Q2", vector_store=vector_store, ollama_client=ollama,
            privacy_budget=budget, user_id="budget-user", epsilon_per_query=0.1,
        )
        assert "budget exhausted" in r2.lower() or "Privacy budget" in r2


def test_dp_noise_changes_scores() -> None:
    """add_dp_noise adds Laplace noise that actually changes values."""
    scores = [0.9, 0.8, 0.7, 0.6, 0.5]
    noisy = add_dp_noise(scores, epsilon=1.0)
    assert len(noisy) == len(scores)
    # At least one score should differ (extremely unlikely all remain identical)
    assert any(abs(n - o) > 1e-10 for n, o in zip(noisy, scores, strict=True))


def test_dpia_generation_five_sections() -> None:
    """DPIA generator produces all 5 GDPR Art. 35 sections."""
    generator = DPIAGenerator()
    report = generator.generate(
        processing_activity="LLM-based citizen query processing",
        data_categories=["personal_data", "health_data", "financial_data"],
        risk_tier=1,
        privacy_budget_remaining=0.3,
    )

    assert report.report_id != ""
    assert report.timestamp > 0
    assert len(report.sections) >= 5
    assert report.risk_level in ("LOW", "MEDIUM", "HIGH", "CRITICAL")

    # Markdown export
    md = generator.to_markdown(report)
    assert "# Data Protection Impact Assessment" in md


def test_privacy_tier_enforced_by_policy() -> None:
    """Policy engine blocks requests with PII when privacy tier is too low."""
    engine = PolicyEngine()

    # PII detected but privacy tier = 0 → violation
    decision = engine.evaluate({
        "role": "viewer",
        "pii_detected": True,
        "privacy_tier": 0,
    })
    assert decision.allowed is False
    assert any("PII" in v for v in decision.violations)

    # PII detected with adequate privacy tier → allowed
    decision2 = engine.evaluate({
        "role": "viewer",
        "pii_detected": True,
        "privacy_tier": 1,
    })
    assert decision2.allowed is True


def test_steer_injects_privacy_context() -> None:
    """STEER injects correct privacy context per tier."""
    for tier in range(4):
        transformed, meta = steer_transform("Test query", privacy_tier=tier)
        assert f"Privacy Level: {tier}" in transformed
        assert meta["privacy_tier"] == tier

    # Tier 3 should mention maximum privacy
    t3, _ = steer_transform("Tell me about the user", privacy_tier=3)
    assert "Privacy Level: 3" in t3
