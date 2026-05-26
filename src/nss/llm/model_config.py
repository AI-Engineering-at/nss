"""Model tier definitions and configuration for APEX routing."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel


class ModelTier(StrEnum):
    """Available model performance tiers."""

    SMALL = "small"
    LARGE = "large"


class ModelConfig(BaseModel):
    """Configuration for a single LLM deployment.

    Attributes:
        name: Ollama model tag (e.g. ``mistral:7b-instruct-v0.3``).
        tier: Performance tier classification.
        max_tokens: Maximum generation length.
        temperature: Sampling temperature.
    """

    name: str
    tier: ModelTier
    max_tokens: int = 2048
    temperature: float = 0.7


AVAILABLE_MODELS: dict[str, ModelConfig] = {
    "mistral:7b-instruct-v0.3": ModelConfig(
        name="mistral:7b-instruct-v0.3",
        tier=ModelTier.SMALL,
        max_tokens=2048,
        temperature=0.7,
    ),
    "mistral-nemo:12b": ModelConfig(
        name="mistral-nemo:12b",
        tier=ModelTier.LARGE,
        max_tokens=4096,
        temperature=0.7,
    ),
}
