"""Async tests for the SENTINEL injection-defence system."""

from unittest.mock import patch

from nss.guardian.sentinel import SentinelDefense
from nss.models import SentinelResult


class TestCheckLLM:
    """Tests for the LLM-based injection check."""

    async def test_check_llm_safe(self, mock_ollama_client) -> None:
        """LLM returning 'SAFE' should not flag as suspicious."""
        mock_ollama_client.generate.return_value = "SAFE"
        sentinel = SentinelDefense(ollama_client=mock_ollama_client)

        result = await sentinel.check_llm("Hello, how are you?")
        assert result is False

    async def test_check_llm_suspicious(self, mock_ollama_client) -> None:
        """LLM returning 'SUSPICIOUS' should flag as suspicious."""
        mock_ollama_client.generate.return_value = "SUSPICIOUS"
        sentinel = SentinelDefense(ollama_client=mock_ollama_client)

        result = await sentinel.check_llm("'; DROP TABLE users; --")
        assert result is True

    async def test_check_llm_exception(self, mock_ollama_client) -> None:
        """LLM raising an exception should fail open (return False)."""
        mock_ollama_client.generate.side_effect = RuntimeError("connection failed")
        sentinel = SentinelDefense(ollama_client=mock_ollama_client)

        result = await sentinel.check_llm("test input")
        assert result is False


class TestCheckInjection:
    """Tests for the aggregated consensus-based injection check."""

    async def test_check_injection_all_safe(self, mock_ollama_client) -> None:
        """When all methods report safe, is_safe should be True."""
        mock_ollama_client.generate.return_value = "SAFE"
        sentinel = SentinelDefense(ollama_client=mock_ollama_client, consensus_threshold=2)

        with patch.object(sentinel, "check_embedding_similarity", return_value=False):
            result = await sentinel.check_injection("Hello, how are you?")

        assert isinstance(result, SentinelResult)
        assert result.is_safe is True
        assert result.method_results["rules"] is True
        assert result.method_results["llm"] is True
        assert result.method_results["embedding"] is True

    async def test_check_injection_rules_flagged(self, mock_ollama_client) -> None:
        """SQL injection text should trigger rules but not reach consensus with threshold=2."""
        mock_ollama_client.generate.return_value = "SAFE"
        sentinel = SentinelDefense(ollama_client=mock_ollama_client, consensus_threshold=2)

        # This text matches the SQL injection regex ("; --" pattern)
        with patch.object(sentinel, "check_embedding_similarity", return_value=False):
            result = await sentinel.check_injection("'; DROP TABLE users; --")

        assert isinstance(result, SentinelResult)
        assert result.method_results["rules"] is False  # rules flagged it
        # Only 1 of 3 methods flagged it (rules), threshold is 2, so still safe
        assert result.is_safe is True
