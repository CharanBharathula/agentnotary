"""
agentnotary.seal
=============
Reproducibility sealing for AI agents — the Cargo.lock for agents.

Public API:
    seal_agent(base_dir) -> AgentLock
    verify_seal(base_dir) -> SealVerifyResult
    diff_seals(a, b) -> list[SealDiff]
"""

from agentnotary.seal.fingerprint import (
    fingerprint_dataset,
    fingerprint_dependencies,
    fingerprint_manifest,
    fingerprint_model,
    fingerprint_prompt,
    fingerprint_tool,
    hash_bytes,
    hash_file,
    hash_text,
)
from agentnotary.seal.lockfile import (
    AgentLock,
    SealDiff,
    SealVerifyResult,
    diff_seals,
    load_lock,
    seal_agent,
    verify_seal,
    write_lock,
)

__all__ = [
    "AgentLock",
    "SealDiff",
    "SealVerifyResult",
    "diff_seals",
    "fingerprint_dataset",
    "fingerprint_dependencies",
    "fingerprint_manifest",
    "fingerprint_model",
    "fingerprint_prompt",
    "fingerprint_tool",
    "hash_bytes",
    "hash_file",
    "hash_text",
    "load_lock",
    "seal_agent",
    "verify_seal",
    "write_lock",
]
