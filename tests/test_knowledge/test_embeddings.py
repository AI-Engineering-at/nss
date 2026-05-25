"""Tests for the embedding service with mocked sentence-transformers."""

from unittest.mock import MagicMock, patch

import numpy as np

from nss.knowledge.embeddings import EmbeddingService


class TestEmbeddingService:
    """Unit tests for EmbeddingService with mocked model."""

    def test_embed_returns_list(self) -> None:
        """embed() should return a list of floats from the model's output."""
        mock_model = MagicMock()
        mock_model.encode.return_value = np.array([0.1] * 384)

        service = EmbeddingService()
        with patch("sentence_transformers.SentenceTransformer", return_value=mock_model):
            service._model = mock_model
            result = service.embed("test text")

        assert isinstance(result, list)
        assert len(result) == 384
        assert all(isinstance(v, float) for v in result)

    def test_embed_batch(self) -> None:
        """embed_batch() should return a list of embedding vectors."""
        mock_model = MagicMock()
        mock_model.encode.return_value = np.array([[0.1] * 384, [0.2] * 384])

        service = EmbeddingService()
        service._model = mock_model
        result = service.embed_batch(["text one", "text two"])

        assert isinstance(result, list)
        assert len(result) == 2
        assert len(result[0]) == 384
        assert len(result[1]) == 384

    def test_lazy_loading(self) -> None:
        """Model should not be loaded until the first embed call."""
        service = EmbeddingService()
        assert service._model is None

        mock_model = MagicMock()
        mock_model.encode.return_value = np.array([0.1] * 384)

        with patch.dict("sys.modules", {"sentence_transformers": MagicMock()}) as _:
            import sys
            sys.modules["sentence_transformers"].SentenceTransformer = MagicMock(
                return_value=mock_model
            )
            service.embed("trigger load")
            assert service._model is not None
