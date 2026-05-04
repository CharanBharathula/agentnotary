"""
agentnotary.attack
===============
Adversarial fuzzer for AI agents.

Bundles a corpus of well-known prompt-injection / jailbreak / data-exfil
attacks (OWASP LLM Top 10, basic Garak-style payloads) and runs them
against the agent's manifest + system prompt to estimate susceptibility.

Public API:
    run_attacks(manifest, ..., suite="owasp-llm-top10") -> AttackReport
"""

from agentnotary.attack.runner import (
    SUPPORTED_SUITES,
    AttackCase,
    AttackReport,
    AttackResult,
    list_corpus,
    run_attacks,
)

__all__ = [
    "AttackCase",
    "AttackReport",
    "AttackResult",
    "SUPPORTED_SUITES",
    "list_corpus",
    "run_attacks",
]
