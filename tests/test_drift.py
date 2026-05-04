"""Tests for drift detection."""

from pathlib import Path

import pytest

from agentnotary.drift import measure_drift, similarity

FIXTURE = Path(__file__).parent / "fixtures" / "agentnotary_v02.yaml"


@pytest.fixture
def sealed_dir(tmp_path):
    (tmp_path / "agentnotary.yaml").write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "system.md").write_text("system", encoding="utf-8")
    from agentnotary.seal import seal_agent, write_lock
    write_lock(seal_agent(str(tmp_path)), str(tmp_path))
    return tmp_path


# ── similarity ────────────────────────────────────────────────────────


def test_similarity_identical_strings():
    assert similarity("hello world", "hello world") == 1.0


def test_similarity_no_overlap():
    assert similarity("hello", "goodbye") == 0.0


def test_similarity_partial_overlap():
    s = similarity("hello world", "hello there")
    assert 0.0 < s < 1.0


def test_similarity_case_insensitive():
    assert similarity("Hello World", "hello world") == 1.0


def test_similarity_both_empty():
    assert similarity("", "") == 1.0


def test_similarity_one_empty():
    assert similarity("hello", "") == 0.0


# ── measure_drift ─────────────────────────────────────────────────────


def test_measure_drift_no_lock_raises(tmp_path):
    (tmp_path / "agentnotary.yaml").write_text("agent:\n  name: x\n  version: 1.0.0\n",
                                                 encoding="utf-8")
    with pytest.raises(FileNotFoundError):
        measure_drift(str(tmp_path))


def test_measure_drift_no_probe_in_seal_returns_skipped(sealed_dir):
    """When `seal` was run without --probe, drift can't be measured."""
    report = measure_drift(str(sealed_dir))
    assert report.probes
    assert report.probes[0].skipped_reason is not None
    assert "no probe" in report.probes[0].skipped_reason.lower()
    assert report.measured_count == 0


def test_measure_drift_basic_fields(sealed_dir):
    report = measure_drift(str(sealed_dir))
    assert report.agent_name == "support-agent"
    assert report.agent_version == "0.3.1"
    assert report.provider == "anthropic"
    assert report.measured_at
    assert report.sealed_at


def test_measure_drift_score_is_zero_when_no_probes_measured(sealed_dir):
    """Score should default to 0 when nothing was measured (not error)."""
    report = measure_drift(str(sealed_dir))
    assert report.drift_score == 0.0
