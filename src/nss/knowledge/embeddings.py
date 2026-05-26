"""Embedding service using ``sentence-transformers``.

Lazy-loads the model on first use to avoid blocking import time.
Default model: ``all-MiniLM-L6-v2`` (384-dimensional embeddings).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

logger = structlog.get_logger(__name__)

_DEFAULT_MODEL_NAME = "all-MiniLM-L6-v2"


class EmbeddingService:
    """Sentence-transformer embedding service with lazy model loading.

    Parameters:
        model_name: HuggingFace model identifier.  Defaults to
            ``all-MiniLM-L6-v2`` which produces 384-dimensional vectors.
    """

    def __init__(self, model_name: str = _DEFAULT_MODEL_NAME) -> None:
        self._model_name = model_name
        self._model: SentenceTransformer | None = None

    def _load_model(self) -> SentenceTransformer:
        """Load the model on first invocation."""
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            logger.info("loading_embedding_model", model=self._model_name)
            self._model = SentenceTransformer(self._model_name)
        return self._model

    def embed(self, text: str) -> list[float]:
        """Embed a single text string.

        Args:
            text: The input text to encode.

        Returns:
            A list of floats representing the embedding vector.
        """
        model = self._load_model()
        embedding = model.encode(text, convert_to_numpy=True)
        result: list[float] = embedding.tolist()
        return result

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of text strings.

        Args:
            texts: List of input texts to encode.

        Returns:
            A list of embedding vectors (one per input text).
        """
        model = self._load_model()
        embeddings = model.encode(texts, convert_to_numpy=True)
        result: list[list[float]] = [e.tolist() for e in embeddings]
        return result
