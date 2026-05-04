"""
agentnotary.drift
=================
Quantify provider-side model drift between the time of seal and now.

The seal records a probe-response hash (when `--probe` was used). `drift`
re-sends the canonical probe(s), captures the new response, and produces:
    - exact-match check (fast)
    - similarity score (cheap, deterministic) — token-level Jaccard
    - per-probe diff for human review

Public API:
    measure_drift(base_dir) -> DriftReport
"""

from agentnotary.drift.detector import (
    DriftReport,
    ProbeDrift,
    measure_drift,
    similarity,
)

__all__ = ["DriftReport", "ProbeDrift", "measure_drift", "similarity"]
