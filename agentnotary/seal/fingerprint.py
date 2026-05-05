"""
agentnotary.seal.fingerprint
=========================
Cryptographic fingerprinting primitives for AgentNotary seal.

Every fingerprint is deterministic and reproducible. SHA-256 is used throughout —
the first 12 chars of the hex digest are surfaced for human-friendly diffs, but
the full 64-char digest is what `agent.lock` records.
"""

from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path
from typing import Optional

import yaml

ALGO = "sha256"
HASH_PREFIX = f"{ALGO}:"


def hash_bytes(data: bytes) -> str:
    return f"{HASH_PREFIX}{hashlib.sha256(data).hexdigest()}"


def hash_text(text: str) -> str:
    return hash_bytes(text.encode("utf-8"))


def hash_file(path: Path) -> Optional[str]:
    """Hash a file's bytes. Returns None if the file is missing."""
    if not path.exists() or not path.is_file():
        return None
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return f"{HASH_PREFIX}{h.hexdigest()}"


# ── Normalization ──────────────────────────────────────────────────────


def _normalize_yaml(text: str) -> bytes:
    """
    Canonicalize a YAML document for stable hashing:
      - parse + re-emit with sorted keys
      - strips comments and whitespace variance
    """
    try:
        parsed = yaml.safe_load(text)
    except yaml.YAMLError:
        # Fall back to whitespace normalization if YAML is invalid
        return _normalize_text(text)
    return yaml.safe_dump(parsed, sort_keys=True, default_flow_style=False).encode("utf-8")


def _normalize_text(text: str) -> bytes:
    """Whitespace-collapsed normalization for prose / prompt files."""
    collapsed = re.sub(r"\s+", " ", text).strip()
    return collapsed.encode("utf-8")


# ── Manifest fingerprint ───────────────────────────────────────────────


def fingerprint_manifest(manifest_path: Path) -> dict:
    """Hash the manifest both raw and normalized."""
    if not manifest_path.exists():
        return {"path": str(manifest_path), "sha256": None, "normalized_sha256": None}
    raw = manifest_path.read_text(encoding="utf-8")
    return {
        "path": str(manifest_path.name),
        "sha256": hash_text(raw),
        "normalized_sha256": hash_bytes(_normalize_yaml(raw)),
        "bytes": len(raw.encode("utf-8")),
    }


# ── Prompt fingerprint ─────────────────────────────────────────────────


def fingerprint_prompt(path: Path) -> dict:
    """Hash a prompt file both raw and whitespace-normalized."""
    if not path.exists():
        return {"path": str(path), "sha256": None, "normalized_sha256": None, "bytes": 0}
    raw = path.read_text(encoding="utf-8", errors="replace")
    return {
        "path": str(path),
        "sha256": hash_text(raw),
        "normalized_sha256": hash_bytes(_normalize_text(raw)),
        "bytes": len(raw.encode("utf-8")),
    }


# ── Model fingerprint ──────────────────────────────────────────────────


# Canonical probe — sent at temperature 0 to detect provider weight updates.
# Designed to elicit a deterministic response across most models.
PROBE_PROMPT = "Reply with exactly one line: AGENTBOX_PROBE_v1_OK"
PROBE_EXPECTED_PREFIX = "AGENTBOX_PROBE_v1"


def fingerprint_model(provider: str, name: str, pinned_version: Optional[str] = None,
                      probe: bool = False) -> dict:
    """
    Fingerprint a model declaration.

    If `probe=True` and the necessary API key is in the env, send the canonical
    probe prompt and hash the response. This is the only way to detect provider
    weight updates that don't change the model name.

    `probe=False` (default) is fast and deterministic; useful for CI and tests.
    """
    fp: dict = {
        "provider": provider,
        "name": name,
        "pinned_version": pinned_version or name,
        "probe_response_hash": None,
        "probe_skipped_reason": None,
    }

    if not probe:
        fp["probe_skipped_reason"] = "probe disabled (run `agentnotary seal --probe` to enable)"
        return fp

    try:
        response = _send_probe(provider, name)
        if response:
            fp["probe_response_hash"] = hash_text(response)
        else:
            fp["probe_skipped_reason"] = "probe returned empty response"
    except Exception as e:  # noqa: BLE001 — probing is best-effort
        fp["probe_skipped_reason"] = f"probe failed: {type(e).__name__}: {e}"

    return fp


def _send_probe(provider: str, model: str) -> Optional[str]:
    """Best-effort canonical probe. Returns None if SDK or API key is missing."""
    import os

    if provider == "anthropic":
        if not os.environ.get("ANTHROPIC_API_KEY"):
            return None
        try:
            import anthropic  # type: ignore[import-not-found]
        except ImportError:
            return None
        client = anthropic.Anthropic()
        resp = client.messages.create(
            model=model,
            max_tokens=64,
            temperature=0,
            messages=[{"role": "user", "content": PROBE_PROMPT}],
        )
        # Extract text content
        text = ""
        for block in resp.content:
            if hasattr(block, "text"):
                text += block.text
        return text.strip()

    if provider == "openai":
        if not os.environ.get("OPENAI_API_KEY"):
            return None
        try:
            import openai  # type: ignore[import-not-found]
        except ImportError:
            return None
        client = openai.OpenAI()
        resp = client.chat.completions.create(
            model=model,
            temperature=0,
            max_tokens=64,
            messages=[{"role": "user", "content": PROBE_PROMPT}],
        )
        return (resp.choices[0].message.content or "").strip()

    return None


# ── Tool fingerprints ──────────────────────────────────────────────────


def fingerprint_tool(tool) -> dict:
    """
    Fingerprint a Tool dataclass.

    For type:
      - function: hash the source via inspect.getsource(module:attr)
      - api: record endpoint + auth env var (no hash; live URL is non-deterministic)
      - mcp: hash the package integrity / pinned_sha if available
      - builtin: name only
    """
    fp = {
        "name": tool.name,
        "type": tool.type,
        "source_sha256": None,
        "endpoint": None,
        "package": None,
        "pinned_sha": None,
    }

    if tool.type == "function" and tool.module:
        fp["source_sha256"] = _hash_function_source(tool.module)

    elif tool.type == "api":
        fp["endpoint"] = tool.endpoint
        fp["auth_env_var"] = tool.auth

    elif tool.type == "mcp":
        fp["command"] = tool.command
        fp["pinned_sha"] = tool.pinned_sha
        # Best-effort: try to extract the npm/PyPI package name
        if tool.command:
            pkg = _extract_mcp_package(tool.command)
            if pkg:
                fp["package"] = pkg

    return fp


def _hash_function_source(module_attr: str) -> Optional[str]:
    """Resolve `pkg.mod:func` and hash its source. Returns None on failure."""
    if ":" not in module_attr:
        return None
    mod_name, attr = module_attr.split(":", 1)
    try:
        import importlib
        import inspect
        mod = importlib.import_module(mod_name)
        obj = getattr(mod, attr, None)
        if obj is None:
            return None
        src = inspect.getsource(obj)
        return hash_text(src)
    except (ImportError, OSError, TypeError, AttributeError):
        return None


def _extract_mcp_package(command: str) -> Optional[str]:
    """
    Heuristic: pull the package name out of an MCP command like
        npx -y @modelcontextprotocol/server-filesystem /data
    """
    parts = command.split()
    for p in parts:
        if p.startswith("@") and "/" in p:
            return p
        if p.startswith("mcp-") or p.endswith("-mcp"):
            return p
    return None


# ── Dataset fingerprints ───────────────────────────────────────────────


def fingerprint_dataset(path: Path, base_dir: Path) -> dict:
    """Hash a dataset file (eval suite, blocked phrases, etc.)."""
    if path.is_absolute():
        full = path
    else:
        full = (base_dir / path).resolve()
    base_resolved = base_dir.resolve()
    try:
        full.resolve().relative_to(base_resolved)
    except ValueError:
        raise ValueError(f"Path escapes project directory: {path}") from None
    return {
        "path": str(path),
        "sha256": hash_file(full),
        "bytes": full.stat().st_size if full.exists() else 0,
    }


# ── Dependencies ───────────────────────────────────────────────────────


def fingerprint_dependencies(base_dir: Path) -> dict:
    """
    Detect and hash whichever Python lockfile is present.
    Order of preference: uv.lock, poetry.lock, requirements.txt.
    """
    candidates = ["uv.lock", "poetry.lock", "Pipfile.lock", "requirements.txt"]
    detected = None
    lock_hash = None
    for c in candidates:
        p = base_dir / c
        if p.exists():
            detected = c
            lock_hash = hash_file(p)
            break

    return {
        "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "lockfile": detected,
        "lockfile_sha256": lock_hash,
    }
