"""
agentnotary.score.scorer
========================
Deterministic governance scoring rubric.

The score is intentionally simple and traceable. Every point gained or lost
cites the rule that fired so users (and CI) can act on the result.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote

from agentnotary.manifest import AgentManifest, parse_manifest, safe_resolve


@dataclass
class ScoreItem:
    """A single scoring rule outcome."""
    dimension: str         # seal | guardrails | attack | compliance | evals | reproducibility | ops
    label: str             # human-readable rule
    points_earned: int
    points_possible: int
    severity: str = "info"  # pass | warn | fail | info
    fix_hint: str = ""      # what the user should do


@dataclass
class ScoreReport:
    score: int                            # 0-100
    items: list = field(default_factory=list)
    grade: str = ""                       # A/B/C/D/F
    summary: str = ""

    def by_dimension(self, dim: str) -> list:
        return [i for i in self.items if i.dimension == dim]

    def fails(self) -> list:
        return [i for i in self.items if i.severity == "fail"]

    def warns(self) -> list:
        return [i for i in self.items if i.severity == "warn"]


# ── Dimension scorers ──────────────────────────────────────────────────


def _score_seal(base_dir: Path, items: list) -> int:
    """20 pts. agent.lock present + manifest hash matches current."""
    from agentnotary.seal import verify_seal
    from agentnotary.seal.lockfile import LOCK_FILENAME

    lockfile = base_dir / LOCK_FILENAME
    if not lockfile.exists():
        items.append(ScoreItem(
            dimension="seal",
            label="agent.lock missing",
            points_earned=0, points_possible=20,
            severity="fail",
            fix_hint="Run: agentnotary seal",
        ))
        return 0

    result = verify_seal(str(base_dir))
    if result.ok:
        items.append(ScoreItem(
            dimension="seal",
            label="agent.lock present and verifies clean",
            points_earned=20, points_possible=20,
            severity="pass",
        ))
        return 20
    items.append(ScoreItem(
        dimension="seal",
        label=f"agent.lock present but drift detected ({len(result.diffs)} change(s))",
        points_earned=8, points_possible=20,
        severity="warn",
        fix_hint="Review changes, then: agentnotary seal",
    ))
    return 8


def _score_guardrails(manifest: AgentManifest, items: list) -> int:
    """20 pts. typed guardrails configured: 4 pts each across cost/iter/tools/pii/rate."""
    spec = manifest.guardrail_spec
    if spec is None:
        items.append(ScoreItem(
            dimension="guardrails",
            label="No typed guardrails declared",
            points_earned=0, points_possible=20,
            severity="fail",
            fix_hint="Add `guardrails:` block to agentnotary.yaml (cost, iterations, tools, pii, rate)",
        ))
        return 0

    earned = 0
    if spec.cost.max_usd_per_session is not None or spec.cost.max_usd_per_call is not None:
        earned += 4
        items.append(ScoreItem(
            dimension="guardrails", label="cost cap configured",
            points_earned=4, points_possible=4, severity="pass",
        ))
    else:
        items.append(ScoreItem(
            dimension="guardrails", label="No cost cap",
            points_earned=0, points_possible=4, severity="warn",
            fix_hint="Add guardrails.cost.max_usd_per_session in agentnotary.yaml",
        ))

    if spec.iterations.max_llm_calls is not None or spec.iterations.max_tool_calls is not None:
        earned += 4
        items.append(ScoreItem(
            dimension="guardrails", label="iteration cap configured",
            points_earned=4, points_possible=4, severity="pass",
        ))
    else:
        items.append(ScoreItem(
            dimension="guardrails", label="No iteration cap (runaway-loop risk)",
            points_earned=0, points_possible=4, severity="warn",
            fix_hint="Add guardrails.iterations.max_llm_calls",
        ))

    if spec.tools.allowlist or spec.tools.denylist:
        earned += 4
        items.append(ScoreItem(
            dimension="guardrails", label="tool allowlist/denylist configured",
            points_earned=4, points_possible=4, severity="pass",
        ))
    else:
        items.append(ScoreItem(
            dimension="guardrails", label="No tool allowlist (any tool can be invoked)",
            points_earned=0, points_possible=4, severity="warn",
            fix_hint="Add guardrails.tools.allowlist with explicit tool names",
        ))

    if spec.pii.patterns:
        earned += 4
        items.append(ScoreItem(
            dimension="guardrails", label=f"PII patterns: {', '.join(spec.pii.patterns)}",
            points_earned=4, points_possible=4, severity="pass",
        ))
    else:
        items.append(ScoreItem(
            dimension="guardrails", label="No PII patterns configured",
            points_earned=0, points_possible=4, severity="warn",
            fix_hint="Add guardrails.pii.patterns: [SSN, EMAIL, CREDIT_CARD]",
        ))

    if spec.rate.max_calls_per_minute is not None or spec.rate.max_calls_per_session is not None:
        earned += 4
        items.append(ScoreItem(
            dimension="guardrails", label="rate limit configured",
            points_earned=4, points_possible=4, severity="pass",
        ))
    else:
        items.append(ScoreItem(
            dimension="guardrails", label="No rate limit",
            points_earned=0, points_possible=4, severity="info",
            fix_hint="Add guardrails.rate.max_calls_per_minute",
        ))

    return earned


def _score_attack(base_dir: Path, manifest: AgentManifest, items: list) -> int:
    """15 pts. Whether `attack` has been run + how the agent fared."""
    # Look for an attack report — we treat absence as 0 pts
    report_path = base_dir / ".agentnotary" / "last_attack.json"
    if not report_path.exists():
        items.append(ScoreItem(
            dimension="attack",
            label="No adversarial test on record",
            points_earned=0, points_possible=15,
            severity="warn",
            fix_hint="Run: agentnotary attack --suite owasp-llm-top10",
        ))
        return 0

    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
        rate = float(report.get("vulnerability_rate", 1.0))
    except (json.JSONDecodeError, ValueError):
        items.append(ScoreItem(
            dimension="attack",
            label="Malformed last_attack.json",
            points_earned=0, points_possible=15,
            severity="warn",
        ))
        return 0

    # Map vuln-rate to points: 0% → 15, 50% → 7, 100% → 0
    earned = max(0, int(15 * (1 - rate)))
    severity = "pass" if rate < 0.2 else ("warn" if rate < 0.5 else "fail")
    items.append(ScoreItem(
        dimension="attack",
        label=f"Adversarial: {int(rate * 100)}% vulnerability rate",
        points_earned=earned, points_possible=15,
        severity=severity,
        fix_hint=("Strengthen system_prompt, add typed PII guardrails, restrict tools"
                  if rate >= 0.2 else ""),
    ))
    return earned


def _score_compliance(manifest: AgentManifest, items: list) -> int:
    """15 pts. Manifest passes compliance --check (no errors)."""
    from agentnotary.compliance import check
    issues = check(manifest)
    errors = [i for i in issues if i.severity == "error"]
    warns = [i for i in issues if i.severity == "warning"]

    if not errors and not warns:
        items.append(ScoreItem(
            dimension="compliance",
            label="Manifest passes compliance --check",
            points_earned=15, points_possible=15,
            severity="pass",
        ))
        return 15
    if not errors:
        items.append(ScoreItem(
            dimension="compliance",
            label=f"Compliance check passes with {len(warns)} warning(s)",
            points_earned=10, points_possible=15,
            severity="warn",
            fix_hint="Run: agentnotary compliance --check",
        ))
        return 10
    items.append(ScoreItem(
        dimension="compliance",
        label=f"Compliance check has {len(errors)} error(s)",
        points_earned=0, points_possible=15,
        severity="fail",
        fix_hint="Run: agentnotary compliance --check",
    ))
    return 0


def _score_evals(manifest: AgentManifest, base_dir: Path, items: list) -> int:
    """10 pts. Eval suite present + non-empty."""
    if not manifest.eval_suite:
        items.append(ScoreItem(
            dimension="evals",
            label="No eval_suite declared in manifest",
            points_earned=0, points_possible=10,
            severity="warn",
            fix_hint="Set agent.eval_suite in agentnotary.yaml",
        ))
        return 0

    eval_path = safe_resolve(base_dir, manifest.eval_suite)
    if not eval_path.exists():
        items.append(ScoreItem(
            dimension="evals",
            label=f"eval_suite path does not exist: {manifest.eval_suite}",
            points_earned=0, points_possible=10,
            severity="warn",
        ))
        return 0

    try:
        import yaml
        suite = yaml.safe_load(eval_path.read_text(encoding="utf-8")) or {}
        cases = suite.get("evals") or suite.get("cases") or []
    except Exception:  # noqa: BLE001
        cases = []

    if len(cases) >= 5:
        items.append(ScoreItem(
            dimension="evals",
            label=f"Eval suite has {len(cases)} cases",
            points_earned=10, points_possible=10,
            severity="pass",
        ))
        return 10
    if len(cases) >= 1:
        items.append(ScoreItem(
            dimension="evals",
            label=f"Eval suite has only {len(cases)} case(s) (recommend ≥5)",
            points_earned=5, points_possible=10,
            severity="warn",
            fix_hint="Add more eval cases to your test_suite.yaml",
        ))
        return 5
    items.append(ScoreItem(
        dimension="evals",
        label="Eval suite is empty",
        points_earned=0, points_possible=10,
        severity="warn",
        fix_hint="Add eval cases to your test_suite.yaml",
    ))
    return 0


def _score_reproducibility(manifest: AgentManifest, base_dir: Path, items: list) -> int:
    """10 pts. Model pinned + prompts in files + deps lockfile."""
    earned = 0

    if manifest.model_spec and manifest.model_spec.pinned_version:
        earned += 4
        items.append(ScoreItem(
            dimension="reproducibility",
            label=f"Model pinned: {manifest.model_spec.pinned_version}",
            points_earned=4, points_possible=4, severity="pass",
        ))
    else:
        items.append(ScoreItem(
            dimension="reproducibility",
            label="Model not pinned (provider may swap weights)",
            points_earned=0, points_possible=4, severity="warn",
            fix_hint="Set agent.model.pinned_version in agentnotary.yaml",
        ))

    if manifest.system_prompt_file:
        earned += 3
        items.append(ScoreItem(
            dimension="reproducibility",
            label="System prompt is in a file (better for diffs)",
            points_earned=3, points_possible=3, severity="pass",
        ))
    elif manifest.system_prompt:
        items.append(ScoreItem(
            dimension="reproducibility",
            label="System prompt inline (consider system_prompt_file)",
            points_earned=1, points_possible=3, severity="info",
        ))
        earned += 1

    # Dep lockfile present?
    deps_present = any((base_dir / fn).exists()
                        for fn in ("uv.lock", "poetry.lock", "Pipfile.lock", "requirements.txt"))
    if deps_present:
        earned += 3
        items.append(ScoreItem(
            dimension="reproducibility",
            label="Python dependency lockfile present",
            points_earned=3, points_possible=3, severity="pass",
        ))
    else:
        items.append(ScoreItem(
            dimension="reproducibility",
            label="No Python dependency lockfile",
            points_earned=0, points_possible=3, severity="warn",
            fix_hint="Generate uv.lock / poetry.lock / requirements.txt for reproducibility",
        ))

    return earned


def _score_ops(base_dir: Path, items: list) -> int:
    """10 pts. Some operational evidence (sessions logged, lock recent)."""
    from agentnotary.recorder import list_sessions

    sessions = list_sessions(str(base_dir))
    if sessions:
        items.append(ScoreItem(
            dimension="ops",
            label=f"{len(sessions)} session(s) recorded",
            points_earned=10, points_possible=10, severity="pass",
        ))
        return 10
    items.append(ScoreItem(
        dimension="ops",
        label="No sessions recorded yet",
        points_earned=0, points_possible=10, severity="info",
        fix_hint="Record a session via `agentnotary guard run -- ...`",
    ))
    return 0


# ── Public API ─────────────────────────────────────────────────────────


def score(base_dir: str = ".") -> ScoreReport:
    """Compute the governance score for the agent in `base_dir`."""
    base = Path(base_dir).resolve()
    items: list[ScoreItem] = []

    try:
        manifest = parse_manifest(str(base))
    except (FileNotFoundError, ValueError) as e:
        return ScoreReport(
            score=0, items=[ScoreItem(
                dimension="manifest",
                label=f"Cannot parse manifest: {e}",
                points_earned=0, points_possible=100,
                severity="fail",
                fix_hint="Run: agentnotary init",
            )],
            grade="F",
            summary="No valid agentnotary.yaml — score is zero.",
        )

    total = 0
    total += _score_seal(base, items)
    total += _score_guardrails(manifest, items)
    total += _score_attack(base, manifest, items)
    total += _score_compliance(manifest, items)
    total += _score_evals(manifest, base, items)
    total += _score_reproducibility(manifest, base, items)
    total += _score_ops(base, items)

    grade = _grade(total)
    summary = _summary(total, items)

    return ScoreReport(score=total, items=items, grade=grade, summary=summary)


def _grade(score: int) -> str:
    if score >= 90:
        return "A"
    if score >= 75:
        return "B"
    if score >= 60:
        return "C"
    if score >= 40:
        return "D"
    return "F"


def _summary(score: int, items: list) -> str:
    fails = sum(1 for i in items if i.severity == "fail")
    warns = sum(1 for i in items if i.severity == "warn")
    if score >= 90:
        return "Excellent. Ship it."
    if score >= 75:
        return f"Strong governance. {warns} optional improvement(s)."
    if score >= 60:
        return f"Decent. Address {warns} warning(s) to improve."
    if score >= 40:
        return f"Significant gaps: {fails} failure(s), {warns} warning(s). Not production-ready."
    return f"Critical: {fails} failure(s). Run `agentnotary doctor` for fixes."


# ── Badge ───────────────────────────────────────────────────────────────


def badge_color(score: int) -> str:
    """shields.io color name based on score."""
    if score >= 90:
        return "brightgreen"
    if score >= 75:
        return "green"
    if score >= 60:
        return "yellowgreen"
    if score >= 40:
        return "yellow"
    if score >= 20:
        return "orange"
    return "red"


def badge_url(score: int) -> str:
    """shields.io static badge URL for the given score."""
    color = badge_color(score)
    label = quote("agentnotary")
    msg = quote(f"{score}/100")
    return f"https://img.shields.io/badge/{label}-{msg}-{color}"


def badge_markdown(score: int, *,
                   link: str = "https://github.com/CharanBharathula/agentnotary") -> str:
    """Drop-in markdown for a README badge."""
    return f"[![AgentNotary Score]({badge_url(score)})]({link})"
