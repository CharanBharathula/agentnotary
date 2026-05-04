"""
agentnotary.guard
==============
Runtime enforcement for AI agents — the active half of governance.

Public API:
    GuardSession — orchestrates the proxy + subprocess + session log
    PolicyEngine — evaluates guardrails against intercepted calls
    run_under_guard(manifest, command, ...) -> GuardResult
"""

from agentnotary.guard.policies import PolicyDecision, PolicyEngine, PolicyViolation
from agentnotary.guard.runner import GuardResult, run_under_guard

__all__ = [
    "GuardResult",
    "PolicyDecision",
    "PolicyEngine",
    "PolicyViolation",
    "run_under_guard",
]
