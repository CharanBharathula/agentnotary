"""
agentnotary.compliance.renderers.json_renderer
===========================================
Render the abstract document tree as structured JSON for ingestion into
GRC tools (OneTrust, ServiceNow GRC, Drata, Vanta).
"""

from __future__ import annotations

from dataclasses import asdict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agentnotary.compliance.generator import ComplianceContext


def render(doc: dict, *, disclaimer: str, ctx: "ComplianceContext") -> dict:
    """Convert the doc tree + context into a flat, GRC-friendly JSON payload."""
    m = ctx.manifest

    return {
        "format_version": "1",
        "format": "agentnotary.compliance/v0.2",
        "standard": "eu-ai-act-annex-iv",
        "disclaimer": disclaimer,
        "generated_at": doc["generated_at"],
        "agent": {
            "name": m.name,
            "version": m.version,
            "description": m.description,
            "author": m.author,
            "framework": m.framework,
            "model": {
                "provider": m.effective_provider,
                "name": m.effective_model,
                "pinned_version": (m.model_spec.pinned_version
                                    if m.model_spec else None),
                "temperature": m.temperature,
                "max_tokens": m.max_tokens,
            },
        },
        "compliance_metadata": (asdict(m.compliance) if m.compliance else None),
        "risk_assessment": {
            "classified_as": ctx.risk.risk_class,
            "declared_as": ctx.risk.declared_risk_class,
            "summary": ctx.risk.summary,
            "fired_rules": [
                {
                    "code": fr.rule.code,
                    "risk_class": fr.rule.risk_class,
                    "description": fr.rule.description,
                    "matched": fr.matched,
                }
                for fr in ctx.risk.fired_rules
            ],
        },
        "guardrails": (asdict(m.guardrail_spec) if m.guardrail_spec else None),
        "tools": [
            {
                "name": t.name,
                "type": t.type,
                "endpoint": t.endpoint,
                "auth_env": t.auth,
                "module": t.module,
            }
            for t in m.tools
        ],
        "seal": ({
            "sealed_at": ctx.lock.sealed_at,
            "sealed_by": ctx.lock.sealed_by,
            "seal_hash": ctx.lock.seal_hash,
            "manifest_hash": ctx.lock.manifest.get("sha256"),
            "probe_response_hash": ctx.lock.model.get("probe_response_hash"),
        } if ctx.lock else None),
        "operational_evidence": ctx.sessions_summary,
        "sections": doc["sections"],
    }
