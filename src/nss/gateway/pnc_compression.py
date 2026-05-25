"""PNC -- Prompt Normalization and Compression.

Reduces prompt size by deduplicating repeated phrases, removing filler
words, and enforcing a token budget to optimize LLM inference cost.
"""

from __future__ import annotations

import re
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# Common filler words/phrases to strip
_FILLER_PATTERNS = [
    r"\b(basically|actually|literally|honestly|obviously|clearly)\b",
    r"\b(you know|I mean|kind of|sort of|like)\b",
    r"\b(um|uh|er|ah|well)\b",
]
_FILLER_RE = re.compile("|".join(_FILLER_PATTERNS), re.IGNORECASE)

# Approximate tokens per word ratio
_TOKENS_PER_WORD = 1.3


def _deduplicate_phrases(text: str) -> str:
    """Remove consecutive duplicate sentences or phrases."""
    sentences = re.split(r"(?<=[.!?])\s+", text)
    seen: set[str] = set()
    unique: list[str] = []
    for s in sentences:
        normalized = s.strip().lower()
        if normalized and normalized not in seen:
            seen.add(normalized)
            unique.append(s.strip())
    return " ".join(unique)


def _remove_fillers(text: str) -> str:
    """Remove common filler words."""
    result = _FILLER_RE.sub("", text)
    return re.sub(r"\s+", " ", result).strip()


def _truncate_to_budget(text: str, max_tokens: int) -> str:
    """Truncate text to approximate token budget."""
    words = text.split()
    max_words = int(max_tokens / _TOKENS_PER_WORD)
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words]) + " [TRUNCATED]"


def compress(
    text: str,
    max_tokens: int = 4096,
    remove_fillers: bool = True,
) -> tuple[str, float, dict[str, Any]]:
    """Compress a prompt for efficient LLM processing.

    Args:
        text: Input text to compress.
        max_tokens: Maximum approximate token budget.
        remove_fillers: Whether to strip filler words.

    Returns:
        Tuple of (compressed_text, compression_ratio, metadata).
        compression_ratio is 1.0 - (compressed_len / original_len).
    """
    original_len = len(text)

    if not text.strip():
        return text, 0.0, {"original_length": 0, "compressed_length": 0, "steps": []}

    steps: list[str] = []
    result = text

    # Step 1: Deduplicate repeated sentences
    deduped = _deduplicate_phrases(result)
    if deduped != result:
        steps.append("deduplication")
        result = deduped

    # Step 2: Remove filler words
    if remove_fillers:
        cleaned = _remove_fillers(result)
        if cleaned != result:
            steps.append("filler_removal")
            result = cleaned

    # Step 3: Token budget truncation
    truncated = _truncate_to_budget(result, max_tokens)
    if truncated != result:
        steps.append("truncation")
        result = truncated

    compressed_len = len(result)
    ratio = 1.0 - (compressed_len / original_len) if original_len > 0 else 0.0

    metadata = {
        "original_length": original_len,
        "compressed_length": compressed_len,
        "compression_ratio": round(ratio, 4),
        "steps": steps,
    }

    logger.info("pnc_compression", **metadata)
    return result, ratio, metadata
