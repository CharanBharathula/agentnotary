"""Smoke tests for CLI commands."""

import pytest
import sys
from pathlib import Path
from unittest.mock import patch

from agentbox.cli import main


MANIFEST = """\
agent:
  name: test-agent
  version: 0.1.0
  model: claude-sonnet-4-20250514
  framework: anthropic
"""


@pytest.fixture(autouse=True)
def isolated_dir(tmp_path, monkeypatch):
    """Run each test in an isolated temp directory."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


def run_cmd(*args):
    """Run CLI and return exit code."""
    with patch("sys.argv", ["agentbox"] + list(args)):
        try:
            return main()
        except SystemExit as e:
            return e.code


def test_init_creates_manifest(isolated_dir):
    run_cmd("init", "my-agent")
    assert (isolated_dir / "agentbox.yaml").exists()


def test_init_creates_evals_dir(isolated_dir):
    run_cmd("init", "my-agent")
    assert (isolated_dir / "evals").exists()
    assert (isolated_dir / "evals" / "test_suite.yaml").exists()


def test_init_creates_prompts_dir(isolated_dir):
    run_cmd("init", "my-agent")
    assert (isolated_dir / "prompts").exists()


def test_init_is_idempotent(isolated_dir):
    run_cmd("init", "my-agent")
    run_cmd("init", "my-agent")  # Should not raise or overwrite
    assert (isolated_dir / "agentbox.yaml").exists()


def test_validate_clean_manifest(isolated_dir):
    (isolated_dir / "agentbox.yaml").write_text(MANIFEST)
    rc = run_cmd("validate")
    assert rc in (0, None)


def test_validate_missing_manifest(isolated_dir):
    rc = run_cmd("validate")
    assert rc == 1


def test_info_shows_agent_data(isolated_dir):
    (isolated_dir / "agentbox.yaml").write_text(MANIFEST)
    rc = run_cmd("info")
    assert rc in (0, None)


def test_info_missing_manifest(isolated_dir):
    rc = run_cmd("info")
    assert rc == 1


def test_tag_creates_version(isolated_dir):
    (isolated_dir / "agentbox.yaml").write_text(MANIFEST)
    rc = run_cmd("tag", "v0.1.0")
    assert rc in (0, None)
    assert (isolated_dir / ".agentbox" / "versions" / "v0.1.0").exists()


def test_versions_empty(isolated_dir):
    (isolated_dir / "agentbox.yaml").write_text(MANIFEST)
    rc = run_cmd("versions")
    assert rc in (0, None)


def test_rollback_missing_version(isolated_dir):
    (isolated_dir / "agentbox.yaml").write_text(MANIFEST)
    rc = run_cmd("rollback", "v99.0.0")
    assert rc == 1


def test_sessions_empty(isolated_dir):
    rc = run_cmd("sessions")
    assert rc in (0, None)


def test_replay_missing_id(isolated_dir):
    rc = run_cmd("replay", "nonexistent-id")
    assert rc == 1


def test_scan_current_directory(isolated_dir):
    (isolated_dir / "agent.py").write_text(
        "import anthropic\nclient = anthropic.Anthropic()\nclient.messages.create(tools=[])\n"
    )
    rc = run_cmd("scan", str(isolated_dir))
    assert rc in (0, None)


def test_help_exits_cleanly():
    rc = run_cmd("--help")
    assert rc in (0, None)


def test_unknown_command_exits():
    rc = run_cmd("does-not-exist")
    assert rc is not None
