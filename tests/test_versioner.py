"""Tests for agent version management."""

import pytest
import json
from pathlib import Path

from agentbox.versioner import (
    compute_agent_hash,
    tag_version,
    list_versions,
    rollback_to,
)

MANIFEST = """\
agent:
  name: test-agent
  version: 0.1.0
  model: claude-sonnet-4-20250514
  framework: anthropic
"""


@pytest.fixture
def agent_project(tmp_path):
    (tmp_path / "agentbox.yaml").write_text(MANIFEST)
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "system.txt").write_text("You are a helpful assistant.")
    (tmp_path / "evals").mkdir()
    (tmp_path / "evals" / "test_suite.yaml").write_text("suite: test\ncases: []")
    (tmp_path / ".agentbox" / "versions").mkdir(parents=True)
    return tmp_path


def test_compute_agent_hash_is_deterministic(agent_project):
    h1 = compute_agent_hash(str(agent_project / "agentbox.yaml"))
    h2 = compute_agent_hash(str(agent_project / "agentbox.yaml"))
    assert h1 == h2
    assert len(h1) == 12


def test_compute_agent_hash_changes_on_content_change(agent_project):
    h1 = compute_agent_hash(str(agent_project / "agentbox.yaml"))
    (agent_project / "agentbox.yaml").write_text(MANIFEST + "\ndescription: changed")
    h2 = compute_agent_hash(str(agent_project / "agentbox.yaml"))
    assert h1 != h2


def test_compute_agent_hash_missing_file(tmp_path):
    result = compute_agent_hash(str(tmp_path / "nonexistent.yaml"))
    assert result == ""


def test_tag_version_creates_directory(agent_project):
    tag_version("v0.1.0", str(agent_project))
    version_dir = agent_project / ".agentbox" / "versions" / "v0.1.0"
    assert version_dir.exists()


def test_tag_version_copies_manifest(agent_project):
    tag_version("v0.1.0", str(agent_project))
    saved = agent_project / ".agentbox" / "versions" / "v0.1.0" / "agentbox.yaml"
    assert saved.exists()
    assert "test-agent" in saved.read_text()


def test_tag_version_copies_prompts(agent_project):
    tag_version("v0.1.0", str(agent_project))
    saved = agent_project / ".agentbox" / "versions" / "v0.1.0" / "prompts" / "system.txt"
    assert saved.exists()


def test_tag_version_writes_version_json(agent_project):
    meta = tag_version("v0.1.0", str(agent_project))
    assert meta["version"] == "v0.1.0"
    assert "tagged_at" in meta
    assert "manifest_hash" in meta

    version_json = agent_project / ".agentbox" / "versions" / "v0.1.0" / "VERSION.json"
    with open(version_json) as f:
        saved_meta = json.load(f)
    assert saved_meta["version"] == "v0.1.0"


def test_tag_version_duplicate_raises(agent_project):
    tag_version("v0.1.0", str(agent_project))
    with pytest.raises(ValueError, match="already exists"):
        tag_version("v0.1.0", str(agent_project))


def test_list_versions_empty(tmp_path):
    (tmp_path / ".agentbox" / "versions").mkdir(parents=True)
    assert list_versions(str(tmp_path)) == []


def test_list_versions_returns_tagged(agent_project):
    tag_version("v0.1.0", str(agent_project))
    tag_version("v0.2.0", str(agent_project))
    versions = list_versions(str(agent_project))
    assert len(versions) == 2
    version_tags = [v["version"] for v in versions]
    assert "v0.1.0" in version_tags
    assert "v0.2.0" in version_tags


def test_rollback_to_restores_manifest(agent_project):
    tag_version("v0.1.0", str(agent_project))
    (agent_project / "agentbox.yaml").write_text(MANIFEST + "\ndescription: new version")
    rollback_to("v0.1.0", str(agent_project))
    content = (agent_project / "agentbox.yaml").read_text()
    assert "description: new version" not in content


def test_rollback_to_auto_saves_current(agent_project):
    tag_version("v0.1.0", str(agent_project))
    (agent_project / "agentbox.yaml").write_text(MANIFEST + "\ndescription: current")
    rollback_to("v0.1.0", str(agent_project))
    # Should have auto-saved current state as pre-rollback-*
    versions = list_versions(str(agent_project))
    pre_rollback = [v for v in versions if "pre-rollback" in v.get("version", "")]
    assert len(pre_rollback) >= 1


def test_rollback_to_missing_version_raises(agent_project):
    with pytest.raises(FileNotFoundError):
        rollback_to("v99.0.0", str(agent_project))
