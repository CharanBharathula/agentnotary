"""
agentnotary.drift.detector
==========================
Re-probes the model and quantifies drift since the last seal.

Without an API key: graceful degradation — reports that drift cannot be
measured and tells the user how to enable it.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from agentnotary.manifest import parse_manifest
from agentnotary.seal.fingerprint import PROBE_PROMPT, _send_probe
from agentnotary.seal.lockfile import load_lock


@dataclass
class ProbeDrift:
    probe_index: int
    prompt: str
    sealed_response_hash: Optional[str]
    current_response_hash: Optional[str]
    sealed_response_preview: str = ""
    current_response_preview: str = ""
    exact_match: bool = False
    similarity_score: float = 0.0     # 0.0 = totally different, 1.0 = identical
    skipped_reason: Optional[str] = None


@dataclass
class DriftReport:
    agent_name: str
    agent_version: str
    sealed_at: str
    measured_at: str
    provider: str
    model: str
    pinned_version: Optional[str]
    probes: list = field(default_factory=list)  # list[ProbeDrift]
    drift_score: float = 0.0           # 0.0 = no drift, 1.0 = totally different
    notes: list = field(default_factory=list)

    @property
    def diverged_count(self) -> int:
        return sum(1 for p in self.probes if not p.exact_match and p.skipped_reason is None)

    @property
    def measured_count(self) -> int:
        return sum(1 for p in self.probes if p.skipped_reason is None)


# ── Similarity ─────────────────────────────────────────────────────────


_TOKEN_RE = re.compile(r"\w+")


def similarity(a: str, b: str) -> float:
    """Token-level Jaccard similarity. Cheap, deterministic, no deps."""
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    ta = set(_TOKEN_RE.findall(a.lower()))
    tb = set(_TOKEN_RE.findall(b.lower()))
    if not ta and not tb:
        return 1.0
    intersection = len(ta & tb)
    union = len(ta | tb)
    return intersection / union if union else 0.0


# ── Detector ───────────────────────────────────────────────────────────


def measure_drift(base_dir: str = ".") -> DriftReport:
    """
    Re-probe the model and produce a drift report comparing to the sealed
    probe-response hash.

    Returns a DriftReport with `probes` populated. If no API key is in env
    or the seal didn't include a probe, individual probes are marked
    `skipped` with a reason.
    """
    base = Path(base_dir).resolve()
    lock = load_lock(str(base))                              # raises if missing
    manifest = parse_manifest(str(base))

    measured_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    provider = manifest.effective_provider
    model = manifest.effective_model
    pinned = (manifest.model_spec.pinned_version
              if manifest.model_spec and manifest.model_spec.pinned_version else None)

    report = DriftReport(
        agent_name=lock.agent_name,
        agent_version=lock.agent_version,
        sealed_at=lock.sealed_at,
        measured_at=measured_at,
        provider=provider, model=model, pinned_version=pinned,
    )

    sealed_probe_hash = lock.model.get("probe_response_hash")
    if not sealed_probe_hash:
        report.notes.append(
            "No probe response was captured at seal time. "
            "Run `agentnotary seal --probe` to enable drift detection."
        )
        report.probes.append(ProbeDrift(
            probe_index=1, prompt=PROBE_PROMPT,
            sealed_response_hash=None, current_response_hash=None,
            skipped_reason="no probe in agent.lock",
        ))
        return report

    # Re-probe (best effort)
    try:
        current_response = _send_probe(provider, model)
    except Exception as e:  # noqa: BLE001
        report.notes.append(f"Probe call failed: {type(e).__name__}: {e}")
        report.probes.append(ProbeDrift(
            probe_index=1, prompt=PROBE_PROMPT,
            sealed_response_hash=sealed_probe_hash, current_response_hash=None,
            skipped_reason=f"probe failed: {type(e).__name__}",
        ))
        return report

    if current_response is None:
        report.notes.append(
            "No API key configured. Set ANTHROPIC_API_KEY or OPENAI_API_KEY "
            "to measure drift live."
        )
        report.probes.append(ProbeDrift(
            probe_index=1, prompt=PROBE_PROMPT,
            sealed_response_hash=sealed_probe_hash, current_response_hash=None,
            skipped_reason="no API key in env",
        ))
        return report

    # Compute current hash + similarity
    current_hash = "sha256:" + hashlib.sha256(current_response.encode("utf-8")).hexdigest()
    exact = (current_hash == sealed_probe_hash)

    # We don't have the original probe response in the lock — only its hash.
    # So similarity here is "current response vs PROBE_PROMPT echo" as a weak
    # signal. The real value is the exact-match boolean.
    # If users want richer drift, they can capture multiple probes (v0.4.x).
    sim = 1.0 if exact else similarity(current_response, PROBE_PROMPT)

    report.probes.append(ProbeDrift(
        probe_index=1, prompt=PROBE_PROMPT,
        sealed_response_hash=sealed_probe_hash,
        current_response_hash=current_hash,
        sealed_response_preview="(only hash captured at seal time)",
        current_response_preview=current_response[:200],
        exact_match=exact,
        similarity_score=sim,
    ))

    measured = report.measured_count or 1
    diverged = report.diverged_count
    report.drift_score = diverged / measured

    if exact:
        report.notes.append("Probe response matches the sealed hash exactly. No drift detected.")
    else:
        report.notes.append(
            "Probe response hash differs from the sealed value. "
            "The model may have been updated by the provider."
        )
        report.notes.append(
            "Note: the sealed lock only stored a hash, not the original response, "
            "so the similarity metric here is approximate. v0.4.x will record full "
            "responses (encrypted at rest) for proper similarity comparison."
        )

    return report
