"""DPIA (Data Protection Impact Assessment) auto-generation.

Generates GDPR Article 35 compliant DPIA reports based on processing
activity descriptions and risk assessment data.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

import structlog

from nss.models import DPIAReport

logger = structlog.get_logger(__name__)

_RISK_LEVEL_MAP = {
    0: "CRITICAL",
    1: "HIGH",
    2: "MEDIUM",
    3: "LOW",
}

_MITIGATION_MAP = {
    "CRITICAL": [
        "Immediate DPO consultation required",
        "Processing must be suspended until review complete",
        "Supervisory authority notification may be required (Art. 36)",
    ],
    "HIGH": [
        "Enhanced Guardian Shield monitoring",
        "SENTINEL consensus threshold increased to 3/3",
        "All responses require manual review",
    ],
    "MEDIUM": [
        "Standard Guardian Shield protections active",
        "PII redaction verified at gateway layer",
        "Audit logging with hash-chain integrity",
    ],
    "LOW": [
        "Standard privacy protections sufficient",
        "Regular audit log review recommended",
    ],
}


class DPIAGenerator:
    """Generate DPIA reports per GDPR Article 35."""

    def generate(
        self,
        processing_activity: str,
        data_categories: list[str],
        risk_tier: int = 3,
        privacy_budget_remaining: float = 1.0,
        additional_context: dict[str, Any] | None = None,
    ) -> DPIAReport:
        """Generate a DPIA report.

        Args:
            processing_activity: Description of the data processing.
            data_categories: Types of personal data involved.
            risk_tier: MARS risk tier (0-3).
            privacy_budget_remaining: Remaining epsilon budget.
            additional_context: Optional extra context.

        Returns:
            A DPIAReport with all 5 required sections.
        """
        report_id = str(uuid.uuid4())
        risk_level = _RISK_LEVEL_MAP.get(risk_tier, "UNKNOWN")
        mitigations = _MITIGATION_MAP.get(risk_level, [])

        sections = {
            "1_description": {
                "title": "Description of Processing",
                "content": processing_activity,
                "data_categories": data_categories,
                "processing_purpose": additional_context.get("purpose", "AI-assisted query processing") if additional_context else "AI-assisted query processing",
            },
            "2_necessity": {
                "title": "Necessity and Proportionality Assessment",
                "content": (
                    f"Processing is conducted under NSS v3.1.1 governance framework. "
                    f"Data minimization enforced via PII redaction at gateway layer. "
                    f"Privacy budget (epsilon): {privacy_budget_remaining:.4f} remaining."
                ),
                "privacy_budget_remaining": privacy_budget_remaining,
                "data_minimization": True,
                "purpose_limitation": True,
            },
            "3_risk_assessment": {
                "title": "Risk Assessment",
                "risk_tier": risk_tier,
                "risk_level": risk_level,
                "content": (
                    f"MARS automated risk scoring classified this activity as "
                    f"{risk_level} (Tier {risk_tier}). "
                    f"Guardian Shield provides 6-layer defensive architecture."
                ),
            },
            "4_mitigation": {
                "title": "Mitigation Measures",
                "measures": mitigations,
                "guardian_shield_active": True,
                "sentinel_active": True,
                "pii_redaction_active": True,
            },
            "5_dpo_consultation": {
                "title": "DPO Consultation Recommendation",
                "required": risk_tier <= 1,
                "recommendation": (
                    "DPO consultation is REQUIRED before proceeding."
                    if risk_tier <= 1
                    else "DPO consultation recommended but not mandatory."
                ),
            },
        }

        recommendation = "PROCEED" if risk_tier >= 2 else "REVIEW_REQUIRED"

        report = DPIAReport(
            report_id=report_id,
            timestamp=int(time.time()),
            sections=sections,
            risk_level=risk_level,
            recommendation=recommendation,
        )

        logger.info("dpia_generated", report_id=report_id, risk_level=risk_level)
        return report

    def to_markdown(self, report: DPIAReport) -> str:
        """Render a DPIA report as Markdown.

        Args:
            report: The DPIA report to render.

        Returns:
            Markdown string.
        """
        lines = [
            "# Data Protection Impact Assessment (DPIA)",
            f"**Report ID:** {report.report_id}",
            f"**Risk Level:** {report.risk_level}",
            f"**Recommendation:** {report.recommendation}",
            "",
        ]

        for key in sorted(report.sections.keys()):
            section = report.sections[key]
            lines.append(f"## {section['title']}")
            if "content" in section:
                lines.append(section["content"])
            if "measures" in section:
                for m in section["measures"]:
                    lines.append(f"- {m}")
            if "recommendation" in section:
                lines.append(f"**{section['recommendation']}**")
            lines.append("")

        return "\n".join(lines)
