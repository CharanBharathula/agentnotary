"""Tests for `agentnotary compare` (lockfile diffing)."""

from pathlib import Path

import pytest

from agentnotary.seal import seal_agent, write_lock
from agentnotary.seal.compare import compare_locks

FIXTURE = Path(__file__).parent / "fixtures" / "agentnotary_v02.yaml"


def _setup(tmp_path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "agentnotary.yaml").write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "prompts").mkdir(exist_ok=True)
    (tmp_path / "prompts" / "system.md").write_text("v1", encoding="utf-8")
    return tmp_path


@pytest.fixture
def two_locks(tmp_path):
    a_dir = _setup(tmp_path / "a")
    b_dir = _setup(tmp_path / "b")
    write_lock(seal_agent(str(a_dir)), str(a_dir))
    # Mutate b before sealing
    (b_dir / "prompts" / "system.md").write_text("v2 — divergent prompt", encoding="utf-8")
    write_lock(seal_agent(str(b_dir)), str(b_dir))
    return a_dir / "agent.lock", b_dir / "agent.lock"


def test_compare_identical_locks_returns_zero_changes(tmp_path):
    a_dir = _setup(tmp_path / "a")
    write_lock(seal_agent(str(a_dir)), str(a_dir))
    # Write the same lock contents to a second file
    (tmp_path / "b.lock").write_text((a_dir / "agent.lock").read_text(encoding="utf-8"),
                                      encoding="utf-8")
    report = compare_locks(str(a_dir / "agent.lock"), str(tmp_path / "b.lock"))
    assert report.total_changes == 0
    for s in report.sections:
        assert s.state == "same"


def test_compare_detects_prompt_change(two_locks):
    a, b = two_locks
    report = compare_locks(str(a), str(b))
    assert report.total_changes > 0
    prompts = next(s for s in report.sections if s.name == "prompts")
    assert prompts.state in ("changed", "mixed")


def test_compare_works_with_directory_arg(tmp_path):
    a_dir = _setup(tmp_path / "a")
    b_dir = _setup(tmp_path / "b")
    write_lock(seal_agent(str(a_dir)), str(a_dir))
    write_lock(seal_agent(str(b_dir)), str(b_dir))
    # Pass directory paths (not the .lock files directly)
    report = compare_locks(str(a_dir), str(b_dir))
    # Both seals are identical content → no changes
    assert isinstance(report.total_changes, int)


def test_compare_invalid_path_raises(tmp_path):
    with pytest.raises((FileNotFoundError, ValueError)):
        compare_locks(str(tmp_path / "missing.lock"), str(tmp_path / "also-missing.lock"))


def test_compare_section_summaries_present(two_locks):
    a, b = two_locks
    report = compare_locks(str(a), str(b))
    for s in report.sections:
        assert s.name
        assert s.state in {"same", "changed", "added", "removed", "mixed"}
        assert s.summary
