"""
agentnotary.compliance.generator
=============================
Top-level orchestrator: load manifest + seal + recent sessions, classify risk,
render the output for the requested standard.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from agentnotary.compliance.classifier import RiskAssessment, classify_risk
from agentnotary.manifest import AgentManifest, parse_manifest
from agentnotary.recorder import list_sessions
from agentnotary.seal.lockfile import AgentLock, load_lock

SUPPORTED_STANDARDS = ["eu-ai-act"]
SUPPORTED_FORMATS = ["markdown", "json", "all"]

DISCLAIMER = (
    "This document is a scaffold generated automatically from declared agent metadata. "
    "It is **NOT legal advice** and does **NOT** constitute a conformity assessment. "
    "Review by qualified counsel and, where required, a notified body is mandatory before "
    "relying on it for regulatory submission. AgentNotary makes no warranty as to the "
    "accuracy or completeness of any field."
)


@dataclass
class ComplianceContext:
    manifest: AgentManifest
    lock: Optional[AgentLock]
    risk: RiskAssessment
    sessions_summary: dict
    generated_at: str
    base_dir: Path


@dataclass
class ComplianceIssue:
    severity: str  # error | warning | info
    field: str
    message: str


@dataclass
class GenerationResult:
    files_written: list = field(default_factory=list)
    risk: Optional[RiskAssessment] = None
    issues: list = field(default_factory=list)


# ── check (CI mode) ────────────────────────────────────────────────────


REQUIRED_FIELDS = [
    ("compliance.intended_purpose", "Required for EU AI Act technical documentation"),
    ("compliance.affected_users", "Required to determine transparency obligations"),
    ("model.pinned_version", "Strongly recommended — auditors expect a pinned model version"),
    ("system_prompt", "Required to document agent behavior"),
]


def check(manifest: AgentManifest) -> list:
    """Validate that the manifest has the fields a compliance generator needs."""
    issues: list[ComplianceIssue] = []
    if not manifest.compliance:
        issues.append(ComplianceIssue(
            severity="error",
            field="agent.compliance",
            message=("No compliance metadata block. Add `compliance:` to agentnotary.yaml "
                     "with at least intended_purpose and affected_users."),
        ))
        return issues

    if not manifest.compliance.intended_purpose:
        issues.append(ComplianceIssue(
            severity="error",
            field="agent.compliance.intended_purpose",
            message="Required field is empty. Describe what the agent does and why.",
        ))

    if not manifest.compliance.affected_users:
        issues.append(ComplianceIssue(
            severity="warning",
            field="agent.compliance.affected_users",
            message="Defaults to 'internal'. Set explicitly: internal, external_consumers, minors, vulnerable_population.",
        ))

    if not manifest.system_prompt and not manifest.system_prompt_file:
        issues.append(ComplianceIssue(
            severity="error",
            field="agent.system_prompt",
            message="No system prompt declared. Required to document agent behavior.",
        ))

    if manifest.model_spec is None or not manifest.model_spec.pinned_version:
        issues.append(ComplianceIssue(
            severity="warning",
            field="agent.model.pinned_version",
            message="Pin the model to a specific version for reproducibility (auditors will ask).",
        ))

    if not manifest.guardrail_spec:
        issues.append(ComplianceIssue(
            severity="warning",
            field="agent.guardrails",
            message="No typed guardrails declared. Required to demonstrate Article 9 risk management.",
        ))

    return issues


# ── generate ───────────────────────────────────────────────────────────


def generate(base_dir: str, standard: str, output_dir: str,
             *, format: str = "all") -> GenerationResult:
    """
    Generate compliance documentation for `standard` and write to `output_dir`.

    Returns a GenerationResult with the list of files written and the risk
    assessment used.
    """
    if standard not in SUPPORTED_STANDARDS:
        raise ValueError(
            f"Unsupported standard '{standard}'. Supported: {', '.join(SUPPORTED_STANDARDS)}"
        )
    if format not in SUPPORTED_FORMATS:
        raise ValueError(
            f"Unsupported format '{format}'. Supported: {', '.join(SUPPORTED_FORMATS)}"
        )

    base = Path(base_dir).resolve()
    out = Path(output_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)

    manifest = parse_manifest(str(base))
    issues = check(manifest)

    # Best-effort seal load
    lock = None
    try:
        lock = load_lock(str(base))
    except FileNotFoundError:
        pass

    risk = classify_risk(manifest)
    sessions = list_sessions(str(base))

    sessions_summary = {
        "total": len(sessions),
        "completed": sum(1 for s in sessions if s.get("status") == "completed"),
        "guardrail_stopped": sum(1 for s in sessions if s.get("status") == "guardrail_stopped"),
        "errors": sum(1 for s in sessions if s.get("status") == "error"),
        "total_cost_usd": round(sum(s.get("cost", 0) for s in sessions), 4),
    }

    ctx = ComplianceContext(
        manifest=manifest,
        lock=lock,
        risk=risk,
        sessions_summary=sessions_summary,
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z",
        base_dir=base,
    )

    files_written: list[Path] = []

    if standard == "eu-ai-act":
        from agentnotary.compliance.standards.eu_ai_act import build_document
        doc = build_document(ctx)

        if format in ("markdown", "all"):
            from agentnotary.compliance.renderers.markdown import render as render_md
            md = render_md(doc, disclaimer=DISCLAIMER)
            md_path = out / "eu_ai_act_annex_iv.md"
            md_path.write_text(md, encoding="utf-8")
            files_written.append(md_path)

        if format in ("json", "all"):
            from agentnotary.compliance.renderers.json_renderer import render as render_json
            payload = render_json(doc, disclaimer=DISCLAIMER, ctx=ctx)
            json_path = out / "eu_ai_act_annex_iv.json"
            json_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
            files_written.append(json_path)

    return GenerationResult(files_written=files_written, risk=risk, issues=issues)
