"""STEER -- Structured Transformation for Enhanced and Efficient Requests.

Transforms user prompts based on privacy tier, detected language, and
normalization rules before passing them to the LLM pipeline.
"""

from __future__ import annotations

import re
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# Simple stopword heuristics for language detection
_GERMAN_MARKERS = {"der", "die", "das", "und", "ist", "ein", "eine", "für", "mit", "von", "auf", "nicht", "ich", "es", "wir", "sie"}
_ENGLISH_MARKERS = {"the", "is", "and", "of", "to", "in", "for", "that", "with", "this", "are", "was", "not", "you", "we"}

_PRIVACY_CONTEXT = {
    0: "Process normally. Standard privacy protections apply.",
    1: "Apply enhanced privacy. Minimize data retention. Redact PII from responses.",
    2: "High privacy mode. No data logging. Ephemeral processing only. Do not reference user history.",
    3: "Maximum privacy. Governance-level restrictions. All outputs must be reviewed before delivery.",
}


def detect_language(text: str) -> str:
    """Detect whether text is primarily German or English.

    Uses a simple stopword frequency heuristic.

    Returns:
        ISO 639-1 code: 'de' or 'en'.
    """
    words = set(text.lower().split())
    de_score = len(words & _GERMAN_MARKERS)
    en_score = len(words & _ENGLISH_MARKERS)
    return "de" if de_score > en_score else "en"


def normalize_prompt(text: str) -> str:
    """Normalize whitespace and quotes in user prompt."""
    # Collapse multiple whitespace
    text = re.sub(r"\s+", " ", text).strip()
    # Normalize smart quotes to standard quotes
    text = text.replace("\u201c", '"').replace("\u201d", '"')
    text = text.replace("\u2018", "'").replace("\u2019", "'")
    return text


def steer_transform(
    message: str,
    privacy_tier: int = 0,
    metadata: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    """Apply STEER transformation pipeline to a user message.

    Steps:
        1. Detect language (DE/EN heuristic).
        2. Normalize prompt (whitespace, quotes).
        3. Inject privacy-tier context.
        4. Apply structured template.

    Args:
        message: Raw user message.
        privacy_tier: Privacy tier (0-3, higher = more restrictive).
        metadata: Optional additional context.

    Returns:
        Tuple of (transformed_message, steer_metadata).
    """
    language = detect_language(message)
    normalized = normalize_prompt(message)
    privacy_context = _PRIVACY_CONTEXT.get(privacy_tier, _PRIVACY_CONTEXT[0])

    # Build structured prompt
    transformed = (
        f"[SYSTEM CONTEXT]\n"
        f"Privacy Level: {privacy_tier}\n"
        f"Privacy Policy: {privacy_context}\n"
        f"Language: {language.upper()}\n"
        f"[END SYSTEM CONTEXT]\n\n"
        f"{normalized}"
    )

    steer_metadata = {
        "language_detected": language,
        "privacy_tier": privacy_tier,
        "original_length": len(message),
        "transformed_length": len(transformed),
        "normalization_applied": message != normalized,
    }

    logger.info("steer_transform", **steer_metadata)
    return transformed, steer_metadata
