"""RAG (Retrieval-Augmented Generation) pipeline.

Combines the EmbeddingService, VectorStore, and SAGEncryptor to
provide a complete retrieval-augmented context injection path.
When ``enable_rag`` is set in the NSS configuration the gateway
will augment prompts with relevant document snippets before
sending them to the LLM.
"""

from __future__ import annotations

from typing import Any

import structlog

from nss.knowledge.sag_encryption import SAGEncryptor

logger = structlog.get_logger(__name__)


class RAGPipeline:
    """Retrieval-augmented generation pipeline.

    Parameters:
        vector_store: A connected ``VectorStore`` instance.
        embedding_service: An ``EmbeddingService`` instance.
        sag_encryptor: Optional ``SAGEncryptor`` for payload decryption.
        top_k: Number of documents to retrieve per query.
    """

    def __init__(
        self,
        vector_store: Any,
        embedding_service: Any,
        sag_encryptor: SAGEncryptor | None = None,
        top_k: int = 5,
    ) -> None:
        self._vs = vector_store
        self._embed = embedding_service
        self._encryptor = sag_encryptor or SAGEncryptor()
        self._top_k = top_k

    async def retrieve(self, query: str) -> list[dict[str, Any]]:
        """Retrieve relevant documents for *query*.

        Returns a list of dicts with ``id``, ``score``, and
        decrypted ``payload`` keys.
        """
        embedding = self._embed.embed(query)
        results: list[dict[str, Any]] = await self._vs.search(
            query_embedding=embedding, top_k=self._top_k
        )

        # Decrypt payloads if encrypted
        for r in results:
            r["payload"] = self._encryptor.decrypt_payload(r.get("payload", {}))

        return results

    async def ingest(
        self,
        doc_id: str,
        text: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Embed and store a document with optional SAG encryption.

        Args:
            doc_id: Unique document identifier.
            text: Document text to embed.
            metadata: Extra metadata stored alongside the vector.
        """
        embedding = self._embed.embed(text)
        payload = {"text": text, **(metadata or {})}

        # Encrypt payload before storing
        encrypted_payload = self._encryptor.encrypt_payload(payload)

        await self._vs.upsert(doc_id=doc_id, embedding=embedding, payload=encrypted_payload)
        logger.info("rag_document_ingested", doc_id=doc_id, encrypted=self._encryptor.enabled)

    def augment_prompt(self, query: str, documents: list[dict[str, Any]]) -> str:
        """Augment a user query with retrieved context.

        Args:
            query: The original user query.
            documents: Retrieved documents from :meth:`retrieve`.

        Returns:
            An augmented prompt containing retrieved context.
        """
        if not documents:
            return query

        context_parts: list[str] = []
        for i, doc in enumerate(documents, 1):
            text = doc.get("payload", {}).get("text", "")
            if text:
                context_parts.append(f"[Document {i}] {text}")

        context_block = "\n".join(context_parts)
        return (
            f"Context from knowledge base:\n{context_block}\n\n"
            f"User query: {query}"
        )
