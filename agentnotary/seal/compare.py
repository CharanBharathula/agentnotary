"""
agentnotary.seal.compare
========================
Higher-level diff between two agent.lock files.

Builds on the existing `diff_seals()` primitive in `lockfile.py` but
projects the output into a developer-friendly summary (model, prompts,
tools, deps — what changed and what stayed the same).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from agentnotary.seal.lockfile import AgentLock, diff_seals


@dataclass
class CompareSection:
    name: str
    state: str            # same | changed | added | removed | mixed
    summary: str          # human-readable line
    details: list = field(default_factory=list)  # supporting diff lines


@dataclass
class CompareReport:
    a_name: str
    b_name: str
    a_path: str
    b_path: str
    sections: list = field(default_factory=list)  # list[CompareSection]
    total_changes: int = 0


def _load(path: str) -> AgentLock:
    p = Path(path)
    if p.is_dir():
        p = p / "agent.lock"
    raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: not a valid lockfile")
    return AgentLock.from_dict(raw)


def compare_locks(path_a: str, path_b: str) -> CompareReport:
    """Compare two lockfiles and return a structured report."""
    a = _load(path_a)
    b = _load(path_b)
    raw_diffs = diff_seals(a, b)

    # Bucket diffs by top-level section
    buckets: dict = {
        "model": [], "prompts": [], "tools": [], "datasets": [],
        "manifest": [], "dependencies": [], "other": [],
    }
    for d in raw_diffs:
        if d.path.startswith("model"):
            buckets["model"].append(d)
        elif d.path.startswith("prompts"):
            buckets["prompts"].append(d)
        elif d.path.startswith("tools"):
            buckets["tools"].append(d)
        elif d.path.startswith("datasets"):
            buckets["datasets"].append(d)
        elif d.path.startswith("manifest"):
            buckets["manifest"].append(d)
        elif d.path.startswith("dependencies"):
            buckets["dependencies"].append(d)
        else:
            buckets["other"].append(d)

    sections = []
    sections.append(_section_for_model(a, b, buckets["model"]))
    sections.append(_section_simple("manifest", buckets["manifest"]))
    sections.append(_section_keyed_list("prompts", buckets["prompts"], a.prompts, b.prompts))
    sections.append(_section_keyed_list("tools", buckets["tools"], a.tools, b.tools))
    sections.append(_section_keyed_list("datasets", buckets["datasets"], a.datasets, b.datasets))
    sections.append(_section_simple("dependencies", buckets["dependencies"]))

    return CompareReport(
        a_name=f"{a.agent_name}@{a.agent_version}",
        b_name=f"{b.agent_name}@{b.agent_version}",
        a_path=path_a,
        b_path=path_b,
        sections=sections,
        total_changes=len(raw_diffs),
    )


def _section_for_model(a: AgentLock, b: AgentLock, diffs: list) -> CompareSection:
    a_name = a.model.get("name", "?")
    b_name = b.model.get("name", "?")
    a_pin = a.model.get("pinned_version", "?")
    b_pin = b.model.get("pinned_version", "?")

    if not diffs:
        return CompareSection(
            name="model", state="same",
            summary=f"unchanged ({a_name} @ {a_pin})",
        )

    summary = f"{a_name} @ {a_pin}  →  {b_name} @ {b_pin}"
    details = [f"{d.path}: {d.before} → {d.after}" for d in diffs]
    return CompareSection(
        name="model", state="changed", summary=summary, details=details,
    )


def _section_simple(name: str, diffs: list) -> CompareSection:
    if not diffs:
        return CompareSection(name=name, state="same", summary="unchanged")
    return CompareSection(
        name=name, state="changed", summary=f"{len(diffs)} change(s)",
        details=[f"{d.path}: {d.before} → {d.after}" for d in diffs],
    )


def _section_keyed_list(name: str, diffs: list, a_list: list, b_list: list) -> CompareSection:
    if not diffs:
        return CompareSection(
            name=name, state="same",
            summary=f"unchanged ({len(a_list)} item(s))",
        )

    added = sum(1 for d in diffs if d.kind == "added")
    removed = sum(1 for d in diffs if d.kind == "removed")
    changed = sum(1 for d in diffs if d.kind == "changed")

    parts = []
    if added:
        parts.append(f"+{added} added")
    if removed:
        parts.append(f"-{removed} removed")
    if changed:
        parts.append(f"~{changed} changed")
    summary = ", ".join(parts) or "unchanged"

    state = "mixed" if (added and removed) else (
        "added" if added and not removed and not changed else
        "removed" if removed and not added and not changed else
        "changed"
    )

    details = []
    for d in diffs:
        if d.kind == "added":
            details.append(f"+ {d.path}")
        elif d.kind == "removed":
            details.append(f"- {d.path}")
        else:
            details.append(f"~ {d.path}")

    return CompareSection(name=name, state=state, summary=summary, details=details)
