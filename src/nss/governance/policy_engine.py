"""Policy engine simulating OPA/Rego policy evaluation.

Uses Python dict-based policies for the reference implementation,
demonstrating the policy-as-code pattern without requiring an external OPA server.
"""

from __future__ import annotations

from typing import Any

import structlog

from nss.models import PolicyDecision

logger = structlog.get_logger(__name__)

# Default policy set
_DEFAULT_POLICIES: dict[str, Any] = {
    "max_risk_tier_for_role": {
        "admin": 0,         # Admin can handle all risk tiers
        "data_processor": 1, # Data processor up to HIGH
        "auditor": 2,       # Auditor up to MEDIUM
        "viewer": 3,        # Viewer only LOW
    },
    "privacy_tier_required_for_pii": 1,  # Minimum tier when PII detected
    "tool_allowlist_per_role": {
        "admin": None,  # None = all tools allowed
        "data_processor": ["search", "calculator", "summarizer", "document_reader", "translator"],
        "auditor": ["search", "document_reader"],
        "viewer": ["search"],
    },
    "max_requests_per_hour": {
        "admin": 10000,
        "data_processor": 1000,
        "auditor": 500,
        "viewer": 100,
    },
}


class PolicyEngine:
    """Evaluate governance policies against request context.

    Args:
        policies: Custom policy dict. Uses defaults if not provided.
    """

    def __init__(self, policies: dict[str, Any] | None = None) -> None:
        self._policies = policies or _DEFAULT_POLICIES
        self._policy_version = "1.0.0"

    def evaluate(self, context: dict[str, Any]) -> PolicyDecision:
        """Evaluate all policies against the given context.

        Args:
            context: Dict with keys like 'role', 'risk_tier', 'pii_detected',
                     'tool_name', 'privacy_tier'.

        Returns:
            PolicyDecision with allowed/violations.
        """
        violations: list[str] = []
        role = context.get("role", "viewer")

        # Check risk tier
        risk_tier = context.get("risk_tier")
        if risk_tier is not None:
            max_tier = self._policies["max_risk_tier_for_role"].get(role, 3)
            if risk_tier < max_tier:  # Lower tier number = higher risk
                violations.append(
                    f"Role '{role}' cannot handle risk tier {risk_tier} "
                    f"(maximum allowed: {max_tier})."
                )

        # Check PII privacy tier
        pii_detected = context.get("pii_detected", False)
        privacy_tier = context.get("privacy_tier", 0)
        min_tier = self._policies["privacy_tier_required_for_pii"]
        if pii_detected and privacy_tier < min_tier:
            violations.append(
                f"PII detected but privacy tier {privacy_tier} < required {min_tier}."
            )

        # Check tool access
        tool_name = context.get("tool_name")
        if tool_name:
            allowed_tools = self._policies["tool_allowlist_per_role"].get(role)
            if allowed_tools is not None and tool_name not in allowed_tools:
                violations.append(
                    f"Role '{role}' not authorized for tool '{tool_name}'."
                )

        allowed = len(violations) == 0

        if not allowed:
            logger.warning("policy_violation", role=role, violations=violations)

        return PolicyDecision(
            allowed=allowed,
            violations=violations,
            policy_version=self._policy_version,
        )
