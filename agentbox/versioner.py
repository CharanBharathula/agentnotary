"""
AgentBox Version Manager
========================
Version, tag, and rollback AI agents.
"""

import json
import shutil
import hashlib
from datetime import datetime, timezone
from pathlib import Path

VERSIONS_DIR = ".agentbox/versions"


def compute_agent_hash(manifest_path: str) -> str:
    """Compute a hash of the agent's full configuration."""
    path = Path(manifest_path)
    if not path.exists():
        return ""
    content = path.read_bytes()
    return hashlib.sha256(content).hexdigest()[:12]


def tag_version(version: str, base_dir: str = "."):
    """Snapshot the current agent state as a tagged version."""
    versions_dir = Path(base_dir) / VERSIONS_DIR
    versions_dir.mkdir(parents=True, exist_ok=True)

    version_dir = versions_dir / version
    if version_dir.exists():
        raise ValueError(f"Version {version} already exists. Use a new version tag.")

    version_dir.mkdir()

    # Copy manifest
    manifest_src = Path(base_dir) / "agentbox.yaml"
    if manifest_src.exists():
        shutil.copy2(manifest_src, version_dir / "agentbox.yaml")

    # Copy prompt files
    prompts_dir = Path(base_dir) / "prompts"
    if prompts_dir.exists():
        shutil.copytree(prompts_dir, version_dir / "prompts", dirs_exist_ok=True)

    # Copy eval suite
    evals_dir = Path(base_dir) / "evals"
    if evals_dir.exists():
        shutil.copytree(evals_dir, version_dir / "evals", dirs_exist_ok=True)

    # Write version metadata
    meta = {
        "version": version,
        "tagged_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
        "manifest_hash": compute_agent_hash(str(manifest_src)),
    }
    with open(version_dir / "VERSION.json", "w") as f:
        json.dump(meta, f, indent=2)

    return meta


def list_versions(base_dir: str = ".") -> list:
    """List all tagged versions."""
    versions_dir = Path(base_dir) / VERSIONS_DIR
    if not versions_dir.exists():
        return []

    versions = []
    for d in sorted(versions_dir.iterdir()):
        if d.is_dir():
            meta_path = d / "VERSION.json"
            if meta_path.exists():
                with open(meta_path) as f:
                    meta = json.load(f)
                versions.append(meta)
            else:
                versions.append({"version": d.name, "tagged_at": "unknown"})

    return versions


def rollback_to(version: str, base_dir: str = "."):
    """Rollback to a tagged version."""
    version_dir = Path(base_dir) / VERSIONS_DIR / version
    if not version_dir.exists():
        raise FileNotFoundError(f"Version {version} not found")

    # Backup current state first
    try:
        tag_version(f"pre-rollback-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}", base_dir)
    except ValueError:
        pass

    # Restore manifest
    saved_manifest = version_dir / "agentbox.yaml"
    if saved_manifest.exists():
        shutil.copy2(saved_manifest, Path(base_dir) / "agentbox.yaml")

    # Restore prompts
    saved_prompts = version_dir / "prompts"
    if saved_prompts.exists():
        target = Path(base_dir) / "prompts"
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(saved_prompts, target)

    # Restore evals
    saved_evals = version_dir / "evals"
    if saved_evals.exists():
        target = Path(base_dir) / "evals"
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(saved_evals, target)

    return {"rolled_back_to": version, "timestamp": datetime.now(timezone.utc).isoformat()}
