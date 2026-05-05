"""
agentnotary.seal.lockfile
======================
Reads, writes, and verifies agent.lock — the cryptographically-hashed
reproducibility snapshot of an AgentNotary agent.

The lockfile schema is YAML (committable, diffable) and stable: future versions
of AgentNotary add fields but don't rename existing ones.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml

from agentnotary.manifest import AgentManifest, parse_manifest, safe_resolve
from agentnotary.seal.fingerprint import (
    HASH_PREFIX,
    fingerprint_dataset,
    fingerprint_dependencies,
    fingerprint_manifest,
    fingerprint_model,
    fingerprint_prompt,
    fingerprint_tool,
)

LOCK_FILENAME = "agent.lock"
LOCK_API_VERSION = "agentnotary/v0.2"


# ── Data classes ───────────────────────────────────────────────────────


@dataclass
class AgentLock:
    api_version: str
    kind: str
    agent_name: str
    agent_version: str
    sealed_at: str
    sealed_by: str
    seal_hash: Optional[str]
    manifest: dict
    model: dict
    prompts: list = field(default_factory=list)
    tools: list = field(default_factory=list)
    datasets: list = field(default_factory=list)
    dependencies: dict = field(default_factory=dict)
    env: dict = field(default_factory=dict)
    non_deterministic: list = field(default_factory=list)

    def to_yaml(self) -> str:
        d = asdict(self)
        return yaml.safe_dump(d, sort_keys=False, default_flow_style=False)

    @classmethod
    def from_dict(cls, d: dict) -> "AgentLock":
        return cls(
            api_version=d.get("api_version", LOCK_API_VERSION),
            kind=d.get("kind", "AgentLock"),
            agent_name=d.get("agent_name", ""),
            agent_version=d.get("agent_version", ""),
            sealed_at=d.get("sealed_at", ""),
            sealed_by=d.get("sealed_by", ""),
            seal_hash=d.get("seal_hash"),
            manifest=d.get("manifest", {}),
            model=d.get("model", {}),
            prompts=d.get("prompts", []),
            tools=d.get("tools", []),
            datasets=d.get("datasets", []),
            dependencies=d.get("dependencies", {}),
            env=d.get("env", {}),
            non_deterministic=d.get("non_deterministic", []),
        )


@dataclass
class SealDiff:
    """A single difference between two seals."""
    kind: str  # added | removed | changed
    path: str  # dot-delimited path into the lockfile
    before: Optional[str] = None
    after: Optional[str] = None


@dataclass
class SealVerifyResult:
    ok: bool
    diffs: list = field(default_factory=list)
    summary: str = ""


# ── Seal generation ────────────────────────────────────────────────────


def _enumerate_non_determinism(manifest: AgentManifest) -> list:
    notes = []
    notes.append(
        "Model provider may silently update underlying weights despite a pinned name "
        "(major providers reserve this right). Run `agentnotary seal --probe` to capture "
        "a probe-response hash that can detect such drift."
    )
    for t in manifest.tools:
        if t.type == "api":
            notes.append(
                f"Tool '{t.name}' calls a live HTTP endpoint ({t.endpoint or 'unspecified'}); "
                "outputs depend on remote service state and are not reproducible."
            )
        elif t.type == "mcp" and not t.pinned_sha:
            notes.append(
                f"MCP server '{t.name}' has no pinned_sha — package upgrades will not be "
                "detected by this seal. Pin a SHA in agentnotary.yaml for stronger guarantees."
            )
        elif t.type == "function" and not t.module:
            notes.append(
                f"Function tool '{t.name}' has no `module:` reference; source code cannot "
                "be hashed. Add `module: pkg.mod:func` for stronger reproducibility."
            )
    return notes


def seal_agent(base_dir: str = ".", *, probe: bool = False,
               sealed_by: Optional[str] = None) -> AgentLock:
    """
    Compute a fresh seal of the agent in `base_dir`.

    Args:
        base_dir: directory containing agentnotary.yaml.
        probe: if True, send the canonical probe prompt and hash the response.
            Requires the relevant provider API key in the environment.
        sealed_by: identifier for who sealed this. Defaults to env vars.
    """
    base = Path(base_dir).resolve()
    manifest = parse_manifest(str(base))

    # Identity
    sealed_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z"
    sealed_by = sealed_by or os.environ.get("AGENTNOTARY_SEALED_BY") \
        or os.environ.get("USER") or os.environ.get("USERNAME") or "unknown"

    # Manifest fingerprint
    manifest_fp = fingerprint_manifest(base / "agentnotary.yaml")

    # Model fingerprint
    model_fp = fingerprint_model(
        provider=manifest.effective_provider,
        name=manifest.effective_model,
        pinned_version=(manifest.model_spec.pinned_version if manifest.model_spec else None),
        probe=probe,
    )
    model_fp["resolved_at"] = sealed_at

    # Prompt fingerprints
    prompt_fps = []
    seen = set()
    if manifest.system_prompt_file:
        p = safe_resolve(base, manifest.system_prompt_file)
        if str(p) not in seen:
            prompt_fps.append(fingerprint_prompt(p))
            seen.add(str(p))
    # Discover any prompts/ directory files
    prompts_dir = base / "prompts"
    if prompts_dir.exists() and prompts_dir.is_dir():
        for f in sorted(prompts_dir.iterdir()):
            if f.is_file() and str(f) not in seen:
                prompt_fps.append(fingerprint_prompt(f))
                seen.add(str(f))

    # Tool fingerprints
    tool_fps = [fingerprint_tool(t) for t in manifest.tools]

    # Dataset fingerprints
    dataset_paths: list[Path] = []
    if manifest.eval_suite:
        dataset_paths.append(safe_resolve(base, manifest.eval_suite))
    # Blocked phrases file from content guardrail
    if manifest.guardrail_spec and manifest.guardrail_spec.content.blocked_phrases_file:
        dataset_paths.append(safe_resolve(base, manifest.guardrail_spec.content.blocked_phrases_file))

    dataset_fps = [fingerprint_dataset(p, base) for p in dataset_paths]

    # Dependencies
    dep_fp = fingerprint_dependencies(base)

    # Env expectations (names only — never values)
    required_vars = list(manifest.env_vars)
    if manifest.entry_point:
        for v in manifest.entry_point.env_vars:
            if v not in required_vars:
                required_vars.append(v)
    for t in manifest.tools:
        if t.auth and t.auth not in required_vars:
            required_vars.append(t.auth)

    env_fp = {
        "required_vars": required_vars,
        "os_hint": os.uname().sysname.lower() if hasattr(os, "uname") else os.name,
    }

    non_det = _enumerate_non_determinism(manifest)

    lock = AgentLock(
        api_version=LOCK_API_VERSION,
        kind="AgentLock",
        agent_name=manifest.name,
        agent_version=manifest.version,
        sealed_at=sealed_at,
        sealed_by=sealed_by,
        seal_hash=None,  # filled below
        manifest=manifest_fp,
        model=model_fp,
        prompts=prompt_fps,
        tools=tool_fps,
        datasets=dataset_fps,
        dependencies=dep_fp,
        env=env_fp,
        non_deterministic=non_det,
    )

    # Compute the rollup hash over the YAML representation of every field except seal_hash
    lock.seal_hash = _compute_seal_hash(lock)
    return lock


def _compute_seal_hash(lock: AgentLock) -> str:
    """Hash the canonical YAML serialization of the lock minus its own seal_hash."""
    d = asdict(lock)
    d["seal_hash"] = None
    canonical = yaml.safe_dump(d, sort_keys=True, default_flow_style=False)
    return f"{HASH_PREFIX}{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"


# ── Persistence ────────────────────────────────────────────────────────


def write_lock(lock: AgentLock, base_dir: str = ".") -> Path:
    path = Path(base_dir) / LOCK_FILENAME
    header = (
        "# AgentNotary Agent Lockfile\n"
        "# Generated by `agentnotary seal`. Commit this file alongside agentnotary.yaml.\n"
        "# Verify integrity with: agentnotary seal --verify\n"
        "# Format: agentnotary/v0.2 — see https://github.com/CharanBharathula/agentnotary\n\n"
    )
    path.write_text(header + lock.to_yaml(), encoding="utf-8")
    return path


def load_lock(base_dir: str = ".") -> AgentLock:
    path = Path(base_dir) / LOCK_FILENAME
    if not path.exists():
        raise FileNotFoundError(f"No {LOCK_FILENAME} found in {base_dir}. Run `agentnotary seal` first.")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"Invalid {LOCK_FILENAME}: expected mapping at root")
    return AgentLock.from_dict(raw)


# ── Verification & diffing ─────────────────────────────────────────────


def verify_seal(base_dir: str = ".") -> SealVerifyResult:
    """Re-fingerprint the agent and diff against the on-disk agent.lock."""
    try:
        existing = load_lock(base_dir)
    except FileNotFoundError as e:
        return SealVerifyResult(ok=False, diffs=[], summary=str(e))

    fresh = seal_agent(base_dir, probe=False)
    diffs = diff_seals(existing, fresh)

    if not diffs:
        return SealVerifyResult(ok=True, diffs=[], summary="Seal verified — no drift detected.")

    return SealVerifyResult(
        ok=False,
        diffs=diffs,
        summary=f"Seal mismatch: {len(diffs)} change(s) detected since last seal.",
    )


def diff_seals(a: AgentLock, b: AgentLock) -> list:
    """Compare two seals and return a list of SealDiff."""
    diffs: list[SealDiff] = []

    # Compare scalar fields
    _diff_scalar(diffs, "manifest.sha256", a.manifest.get("sha256"), b.manifest.get("sha256"))
    _diff_scalar(diffs, "manifest.normalized_sha256",
                 a.manifest.get("normalized_sha256"), b.manifest.get("normalized_sha256"))
    _diff_scalar(diffs, "model.name", a.model.get("name"), b.model.get("name"))
    _diff_scalar(diffs, "model.pinned_version",
                 a.model.get("pinned_version"), b.model.get("pinned_version"))
    _diff_scalar(diffs, "model.probe_response_hash",
                 a.model.get("probe_response_hash"), b.model.get("probe_response_hash"))
    _diff_scalar(diffs, "dependencies.lockfile_sha256",
                 a.dependencies.get("lockfile_sha256"), b.dependencies.get("lockfile_sha256"))

    # Compare prompt list keyed by path
    _diff_keyed_list(diffs, "prompts", a.prompts, b.prompts, key="path",
                     compare_fields=["sha256", "normalized_sha256"])
    _diff_keyed_list(diffs, "tools", a.tools, b.tools, key="name",
                     compare_fields=["source_sha256", "endpoint", "pinned_sha", "package"])
    _diff_keyed_list(diffs, "datasets", a.datasets, b.datasets, key="path",
                     compare_fields=["sha256"])

    return diffs


def _diff_scalar(diffs, path, before, after):
    if before != after:
        diffs.append(SealDiff(kind="changed", path=path, before=str(before), after=str(after)))


def _diff_keyed_list(diffs, prefix, a_list, b_list, *, key, compare_fields):
    a_map = {item.get(key): item for item in a_list if item.get(key)}
    b_map = {item.get(key): item for item in b_list if item.get(key)}

    for k in sorted(set(a_map) - set(b_map)):
        diffs.append(SealDiff(kind="removed", path=f"{prefix}[{k}]", before=str(a_map[k])))
    for k in sorted(set(b_map) - set(a_map)):
        diffs.append(SealDiff(kind="added", path=f"{prefix}[{k}]", after=str(b_map[k])))
    for k in sorted(set(a_map) & set(b_map)):
        for field_name in compare_fields:
            av = a_map[k].get(field_name)
            bv = b_map[k].get(field_name)
            if av != bv:
                diffs.append(SealDiff(
                    kind="changed",
                    path=f"{prefix}[{k}].{field_name}",
                    before=str(av),
                    after=str(bv),
                ))
