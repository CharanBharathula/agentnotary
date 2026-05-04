"""Tests for agentnotary.seal — fingerprinting and lockfile."""

from pathlib import Path

import pytest

from agentnotary.seal import (
    diff_seals,
    hash_bytes,
    hash_file,
    hash_text,
    load_lock,
    seal_agent,
    verify_seal,
    write_lock,
)
from agentnotary.seal.fingerprint import (
    _normalize_yaml,
    fingerprint_dependencies,
    fingerprint_manifest,
    fingerprint_prompt,
)

FIXTURE = Path(__file__).parent / "fixtures" / "agentnotary_v02.yaml"


@pytest.fixture
def sealed_dir(tmp_path):
    (tmp_path / "agentnotary.yaml").write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "system.md").write_text(
        "You are the support agent.", encoding="utf-8"
    )
    (tmp_path / "evals").mkdir()
    (tmp_path / "evals" / "test_suite.yaml").write_text(
        "evals:\n  - name: greet\n    input: hi\n    expected_behavior: greets back\n",
        encoding="utf-8",
    )
    (tmp_path / ".agentnotary" / "sessions").mkdir(parents=True)
    return tmp_path


# ── Hash primitives ─────────────────────────────────────────────────────


def test_hash_bytes_deterministic():
    assert hash_bytes(b"hello") == hash_bytes(b"hello")


def test_hash_text_format():
    h = hash_text("hello")
    assert h.startswith("sha256:")
    assert len(h) == len("sha256:") + 64


def test_hash_file_missing_returns_none(tmp_path):
    assert hash_file(tmp_path / "nope.txt") is None


def test_hash_file_consistency(tmp_path):
    p = tmp_path / "f.txt"
    p.write_text("data", encoding="utf-8")
    assert hash_file(p) == hash_text("data")


# ── Normalization ───────────────────────────────────────────────────────


def test_normalize_yaml_ignores_comments():
    a = "name: foo\nversion: 1.0\n"
    b = "# top comment\nname: foo\n# inline\nversion: 1.0\n"
    assert _normalize_yaml(a) == _normalize_yaml(b)


def test_normalize_yaml_ignores_key_order():
    a = "name: foo\nversion: 1.0\n"
    b = "version: 1.0\nname: foo\n"
    assert _normalize_yaml(a) == _normalize_yaml(b)


# ── Manifest fingerprint ────────────────────────────────────────────────


def test_fingerprint_manifest_has_both_hashes(sealed_dir):
    fp = fingerprint_manifest(sealed_dir / "agentnotary.yaml")
    assert fp["sha256"] is not None
    assert fp["normalized_sha256"] is not None
    assert fp["bytes"] > 0


def test_fingerprint_manifest_missing(tmp_path):
    fp = fingerprint_manifest(tmp_path / "missing.yaml")
    assert fp["sha256"] is None


# ── Prompt fingerprint ──────────────────────────────────────────────────


def test_fingerprint_prompt_normalization(tmp_path):
    a = tmp_path / "a.md"
    b = tmp_path / "b.md"
    a.write_text("Hello world", encoding="utf-8")
    b.write_text("Hello   world  ", encoding="utf-8")  # extra whitespace
    fa = fingerprint_prompt(a)
    fb = fingerprint_prompt(b)
    assert fa["sha256"] != fb["sha256"]  # raw differs
    assert fa["normalized_sha256"] == fb["normalized_sha256"]  # normalized matches


# ── Dependencies ────────────────────────────────────────────────────────


def test_fingerprint_dependencies_no_lockfile(tmp_path):
    fp = fingerprint_dependencies(tmp_path)
    assert fp["python"]
    assert fp["lockfile"] is None


def test_fingerprint_dependencies_with_requirements(tmp_path):
    (tmp_path / "requirements.txt").write_text("anthropic==0.40\n", encoding="utf-8")
    fp = fingerprint_dependencies(tmp_path)
    assert fp["lockfile"] == "requirements.txt"
    assert fp["lockfile_sha256"] is not None


# ── End-to-end seal ─────────────────────────────────────────────────────


def test_seal_writes_agent_lock(sealed_dir):
    lock = seal_agent(str(sealed_dir))
    path = write_lock(lock, str(sealed_dir))
    assert path.exists()
    assert path.name == "agent.lock"


def test_seal_includes_required_fields(sealed_dir):
    lock = seal_agent(str(sealed_dir))
    assert lock.agent_name == "support-agent"
    assert lock.agent_version == "0.3.1"
    assert lock.seal_hash and lock.seal_hash.startswith("sha256:")
    assert lock.manifest["sha256"]
    assert lock.model["provider"] == "anthropic"
    assert len(lock.prompts) >= 1  # system.md
    assert len(lock.tools) >= 2
    assert len(lock.datasets) >= 1
    assert lock.non_deterministic  # always at least one caveat


def test_seal_hash_is_deterministic_for_same_content(sealed_dir):
    lock1 = seal_agent(str(sealed_dir))
    lock2 = seal_agent(str(sealed_dir))
    # Manifest and prompt hashes should match across runs
    assert lock1.manifest["sha256"] == lock2.manifest["sha256"]
    assert sorted(p["sha256"] for p in lock1.prompts) == sorted(p["sha256"] for p in lock2.prompts)


def test_load_lock_round_trip(sealed_dir):
    original = seal_agent(str(sealed_dir))
    write_lock(original, str(sealed_dir))
    loaded = load_lock(str(sealed_dir))
    assert loaded.agent_name == original.agent_name
    assert loaded.seal_hash == original.seal_hash


def test_load_lock_missing_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_lock(str(tmp_path))


def test_verify_seal_clean(sealed_dir):
    lock = seal_agent(str(sealed_dir))
    write_lock(lock, str(sealed_dir))
    result = verify_seal(str(sealed_dir))
    assert result.ok is True
    assert result.diffs == []


def test_verify_seal_detects_manifest_change(sealed_dir):
    lock = seal_agent(str(sealed_dir))
    write_lock(lock, str(sealed_dir))
    # Mutate the manifest semantically
    p = sealed_dir / "agentnotary.yaml"
    p.write_text(p.read_text(encoding="utf-8") + "\n# breaking change\n", encoding="utf-8")
    # Force a real semantic diff so normalized hash also changes
    p.write_text(p.read_text(encoding="utf-8").replace("temperature: 0.2", "temperature: 0.5"),
                  encoding="utf-8")
    result = verify_seal(str(sealed_dir))
    assert result.ok is False
    paths = [d.path for d in result.diffs]
    assert any("manifest" in p for p in paths)


def test_verify_seal_detects_prompt_change(sealed_dir):
    lock = seal_agent(str(sealed_dir))
    write_lock(lock, str(sealed_dir))
    (sealed_dir / "prompts" / "system.md").write_text("DIFFERENT PROMPT", encoding="utf-8")
    result = verify_seal(str(sealed_dir))
    assert result.ok is False
    assert any("prompts" in d.path for d in result.diffs)


def test_diff_seals_reports_added_prompt(sealed_dir):
    lock_a = seal_agent(str(sealed_dir))
    (sealed_dir / "prompts" / "extra.md").write_text("New prompt", encoding="utf-8")
    lock_b = seal_agent(str(sealed_dir))
    diffs = diff_seals(lock_a, lock_b)
    assert any(d.kind == "added" and "prompts" in d.path for d in diffs)
