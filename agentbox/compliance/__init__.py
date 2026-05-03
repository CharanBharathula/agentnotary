"""
agentbox.compliance
===================
Compliance documentation generator for AI agents.

Combines manifest + seal + recent sessions + scan results into regulatory
documentation packages. Currently supports EU AI Act Annex IV.

Public API:
    generate(base_dir, standard, output_dir) -> GenerationResult
    check(manifest) -> list[ComplianceIssue]
"""

from agentbox.compliance.classifier import RiskAssessment, classify_risk
from agentbox.compliance.generator import (
    ComplianceContext,
    ComplianceIssue,
    GenerationResult,
    check,
    generate,
)

__all__ = [
    "ComplianceContext",
    "ComplianceIssue",
    "GenerationResult",
    "RiskAssessment",
    "check",
    "classify_risk",
    "generate",
]
