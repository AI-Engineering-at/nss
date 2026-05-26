"""Tests for the DPSparseVoteRAG privacy-preserving retrieval pipeline."""

from unittest.mock import MagicMock, patch

import pytest

from nss.agent.dp_sparse_vote import add_dp_noise, dpsparsevote_rag
from nss.governance.privacy_budget import PrivacyBudgetTracker


class TestAddDPNoise:
    """Unit tests for the add_dp_noise function."""

    def test_add_dp_noise_same_length(self) -> None:
        """Output list should have the same length as the input."""
        values = [0.5, 0.8, 0.3, 0.9]
        noisy = add_dp_noise(values, epsilon=1.0)
        assert len(noisy) == len(values)

    def test_add_dp_noise_large_epsilon(self) -> None:
        """Large epsilon should produce values close to the originals."""
        values = [0.5, 0.8, 0.3, 0.9]
        epsilon = 100.0
        noisy = add_dp_noise(values, epsilon=epsilon)

        for original, noised in zip(values, noisy, strict=True):
            assert abs(original - noised) < 0.5  # tight bound with large epsilon

    def test_add_dp_noise_small_epsilon(self) -> None:
        """Small epsilon should produce more divergent values (statistical test)."""
        values = [0.5] * 100
        epsilon = 0.01
        noisy = add_dp_noise(values, epsilon=epsilon)

        # With very small epsilon, at least some values should be far from 0.5
        max_deviation = max(abs(n - 0.5) for n in noisy)
        assert max_deviation > 1.0  # Laplace(0, 100) will have large spread

    def test_add_dp_noise_negative_epsilon_raises(self) -> None:
        """Negative epsilon should raise ValueError."""
        with pytest.raises(ValueError, match="Epsilon must be positive"):
            add_dp_noise([0.5], epsilon=-1.0)


class TestDPSparseVoteRAG:
    """Tests for the dpsparsevote_rag async function."""

    async def test_dpsparsevote_rag_happy_path(
        self, mock_ollama_client, mock_vector_store
    ) -> None:
        """Happy path: budget available, candidates found, response generated."""
        budget = PrivacyBudgetTracker(total_budget=1.0)
        mock_ollama_client.generate.return_value = "Generated answer based on context."

        # Mock the EmbeddingService used inside dpsparsevote_rag
        mock_embedder = MagicMock()
        mock_embedder.embed.return_value = [0.1] * 384

        with patch(
            "nss.knowledge.embeddings.EmbeddingService", return_value=mock_embedder
        ):
            result = await dpsparsevote_rag(
                query="What is GDPR?",
                vector_store=mock_vector_store,
                ollama_client=mock_ollama_client,
                privacy_budget=budget,
                user_id="user-1",
            )

        assert result == "Generated answer based on context."
        mock_ollama_client.generate.assert_awaited()
        mock_vector_store.search.assert_awaited_once()

    async def test_dpsparsevote_rag_budget_exhausted(
        self, mock_ollama_client, mock_vector_store
    ) -> None:
        """When privacy budget is exhausted, return an error message."""
        budget = PrivacyBudgetTracker(total_budget=0.01)
        # Exhaust the budget first
        budget.consume(0.01, "user-1")

        result = await dpsparsevote_rag(
            query="What is GDPR?",
            vector_store=mock_vector_store,
            ollama_client=mock_ollama_client,
            privacy_budget=budget,
            user_id="user-1",
            epsilon_per_query=0.1,
        )

        assert "Privacy budget exhausted" in result
        assert "user-1" in result

    async def test_dpsparsevote_rag_no_candidates(
        self, mock_ollama_client, mock_vector_store
    ) -> None:
        """When no candidates are found, fall back to LLM-only response."""
        budget = PrivacyBudgetTracker(total_budget=1.0)
        mock_vector_store.search.return_value = []
        mock_ollama_client.generate.return_value = "LLM-only fallback answer."

        mock_embedder = MagicMock()
        mock_embedder.embed.return_value = [0.1] * 384

        with patch(
            "nss.knowledge.embeddings.EmbeddingService", return_value=mock_embedder
        ):
            result = await dpsparsevote_rag(
                query="What is GDPR?",
                vector_store=mock_vector_store,
                ollama_client=mock_ollama_client,
                privacy_budget=budget,
                user_id="user-1",
            )

        assert result == "LLM-only fallback answer."
