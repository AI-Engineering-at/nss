"""Tests for the RAG (Retrieval-Augmented Generation) pipeline."""

from __future__ import annotations

from typing import Any

import pytest

from nss.knowledge.rag_pipeline import RAGPipeline
from nss.knowledge.sag_encryption import SAGEncryptor

# -- Fixtures ----------------------------------------------------------------


class FakeEmbeddingService:
    """Deterministic embedding service for tests."""

    def embed(self, text: str) -> list[float]:
        return [float(len(text) % 10)] * 384


class FakeVectorStore:
    """In-memory vector store mock."""

    def __init__(self) -> None:
        self._data: dict[str, dict[str, Any]] = {}

    async def search(
        self,
        query_embedding: list[float],
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        results = []
        for doc_id, item in list(self._data.items())[:top_k]:
            results.append({
                "id": doc_id,
                "score": 0.9,
                "payload": item["payload"],
            })
        return results

    async def upsert(
        self,
        doc_id: str,
        embedding: list[float],
        payload: dict[str, Any],
    ) -> None:
        self._data[doc_id] = {"embedding": embedding, "payload": payload}


# -- Tests -------------------------------------------------------------------


class TestRAGPipeline:
    """RAG pipeline tests."""

    @pytest.fixture
    def pipeline(self) -> RAGPipeline:
        return RAGPipeline(
            vector_store=FakeVectorStore(),
            embedding_service=FakeEmbeddingService(),
        )

    @pytest.fixture
    def encrypted_pipeline(self) -> tuple[RAGPipeline, FakeVectorStore]:
        import os
        key = os.urandom(32).hex()
        vs = FakeVectorStore()
        enc = SAGEncryptor(hex_key=key)
        pipe = RAGPipeline(
            vector_store=vs,
            embedding_service=FakeEmbeddingService(),
            sag_encryptor=enc,
        )
        return pipe, vs

    async def test_ingest_and_retrieve(self, pipeline: RAGPipeline):
        """Ingest a document and retrieve it."""
        await pipeline.ingest("doc1", "This is test content", {"author": "test"})
        results = await pipeline.retrieve("test content")
        assert len(results) == 1
        assert results[0]["payload"]["text"] == "This is test content"
        assert results[0]["payload"]["author"] == "test"

    async def test_retrieve_empty_store(self, pipeline: RAGPipeline):
        """Retrieving from empty store returns empty list."""
        results = await pipeline.retrieve("anything")
        assert results == []

    async def test_augment_prompt_with_documents(self, pipeline: RAGPipeline):
        """augment_prompt injects retrieved context."""
        docs = [
            {"payload": {"text": "Document A content"}},
            {"payload": {"text": "Document B content"}},
        ]
        augmented = pipeline.augment_prompt("What is X?", docs)
        assert "Context from knowledge base:" in augmented
        assert "[Document 1] Document A content" in augmented
        assert "[Document 2] Document B content" in augmented
        assert "User query: What is X?" in augmented

    async def test_augment_prompt_no_documents(self, pipeline: RAGPipeline):
        """Without documents, prompt is returned unchanged."""
        result = pipeline.augment_prompt("Hello", [])
        assert result == "Hello"

    async def test_encrypted_ingest_and_retrieve(
        self,
        encrypted_pipeline: tuple[RAGPipeline, FakeVectorStore],
    ):
        """Encrypted pipeline: data is encrypted at rest, decrypted on read."""
        pipe, vs = encrypted_pipeline
        await pipe.ingest("doc1", "Secret document", {"level": "classified"})

        # Verify data is encrypted in the store
        stored = vs._data["doc1"]["payload"]
        assert "_sag_encrypted" in stored
        assert "text" not in stored

        # Retrieve decrypts automatically
        results = await pipe.retrieve("secret")
        assert results[0]["payload"]["text"] == "Secret document"
        assert results[0]["payload"]["level"] == "classified"
