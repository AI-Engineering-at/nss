"""DPSparseVoteRAG -- differentially private sparse-vote retrieval-augmented generation.

Adds calibrated Laplace noise to similarity scores before selecting context
documents, then consumes the corresponding epsilon from the user's privacy
budget.
"""

from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from nss.governance.privacy_budget import PrivacyBudgetTracker
    from nss.knowledge.vector_store import VectorStore
    from nss.llm.ollama_client import OllamaClient

logger = structlog.get_logger(__name__)


def add_dp_noise(values: list[float], epsilon: float) -> list[float]:
    """Add Laplace noise calibrated to *epsilon* to each value.

    The Laplace mechanism adds noise drawn from ``Lap(0, 1/epsilon)`` to
    each element, providing epsilon-differential privacy for a sensitivity-1
    query.

    Args:
        values: Raw numeric values (e.g. similarity scores).
        epsilon: Privacy parameter -- smaller means more noise.

    Returns:
        A new list with noise added to each element.
    """
    if epsilon <= 0:
        raise ValueError("Epsilon must be positive.")

    scale = 1.0 / epsilon
    noisy: list[float] = []
    for v in values:
        # Laplace noise via inverse CDF: Lap(0, b) = -b * sign(u) * ln(1 - 2|u|)
        u = random.random() - 0.5
        noise = -scale * math.copysign(1, u) * math.log(1 - 2 * abs(u))
        noisy.append(v + noise)
    return noisy


async def dpsparsevote_rag(
    query: str,
    vector_store: VectorStore,
    ollama_client: OllamaClient,
    privacy_budget: PrivacyBudgetTracker,
    user_id: str,
    top_k: int = 5,
    epsilon_per_query: float = 0.1,
) -> str:
    """Execute a privacy-preserving RAG pipeline.

    Steps:
        1. Embed the *query*.
        2. Retrieve candidate documents from the vector store.
        3. Add Laplace noise to the similarity scores.
        4. Re-rank by noisy scores and select the top-k.
        5. Consume epsilon from the user's privacy budget.
        6. Generate a response conditioned on the selected context.

    Args:
        query: The user's natural-language question.
        vector_store: Qdrant vector store instance.
        ollama_client: Ollama LLM client.
        privacy_budget: Privacy budget tracker.
        user_id: Requesting user's identifier.
        top_k: Number of context documents to use.
        epsilon_per_query: Epsilon consumed per query.

    Returns:
        The generated answer string.  Returns an error message if the
        privacy budget is exhausted.
    """
    # Check budget first
    if not privacy_budget.consume(epsilon_per_query, user_id):
        remaining = privacy_budget.remaining(user_id)
        return (
            f"Privacy budget exhausted for user {user_id}. "
            f"Remaining epsilon: {remaining:.4f}. "
            "Please contact your administrator to reset your budget."
        )

    # Embed the query (import here to avoid circular deps at module level)
    from nss.knowledge.embeddings import EmbeddingService

    embedder = EmbeddingService()
    query_embedding = embedder.embed(query)

    # Retrieve candidates (fetch more than top_k so noise has room to re-rank)
    candidates: list[dict[str, Any]] = await vector_store.search(
        query_embedding=query_embedding,
        top_k=top_k * 3,
    )

    if not candidates:
        return await ollama_client.generate(
            prompt=query,
            system_prompt="No relevant context was found.  Answer to the best of your ability.",
        )

    # Add DP noise to scores and re-rank
    scores = [c["score"] for c in candidates]
    noisy_scores = add_dp_noise(scores, epsilon_per_query)

    ranked = sorted(
        zip(candidates, noisy_scores, strict=True),
        key=lambda pair: pair[1],
        reverse=True,
    )
    selected = [doc for doc, _score in ranked[:top_k]]

    # Build context block
    context_parts = []
    for i, doc in enumerate(selected, 1):
        text = doc.get("payload", {}).get("text", "")
        context_parts.append(f"[{i}] {text}")
    context_block = "\n\n".join(context_parts)

    # Generate answer
    prompt = (
        f"Context documents:\n{context_block}\n\n"
        f"Question: {query}\n\n"
        "Answer the question using ONLY the provided context.  "
        "If the context is insufficient, say so."
    )

    response = await ollama_client.generate(prompt=prompt)

    logger.info(
        "dpsparsevote_rag_complete",
        user_id=user_id,
        candidates=len(candidates),
        selected=len(selected),
        epsilon_consumed=epsilon_per_query,
    )

    return response
