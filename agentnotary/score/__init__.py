"""
agentnotary.score
=================
Governance score (0-100) + actionable punch-list.

The score is a deterministic rubric over six dimensions:
  - seal status (20 pts) — agent.lock present & verifies
  - typed guardrails (20 pts) — cost / iter / tools / pii / rate configured
  - adversarial coverage (15 pts) — `attack` has been run; pass-rate factored
  - compliance readiness (15 pts) — manifest passes `compliance --check`
  - eval coverage (10 pts) — eval suite present & non-trivial
  - reproducibility (10 pts) — model pinned, prompts in files, deps lockfile
  - operational hygiene (10 pts) — sessions logged, recent activity

Public API:
    score(base_dir) -> ScoreReport
    badge_url(score) -> str
"""

from agentnotary.score.scorer import (
    ScoreItem,
    ScoreReport,
    badge_color,
    badge_url,
    score,
)

__all__ = ["ScoreItem", "ScoreReport", "badge_color", "badge_url", "score"]
