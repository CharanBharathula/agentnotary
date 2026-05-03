"""Tests for the manifest parser and validator."""

import pytest
import tempfile
import os
from pathlib import Path

from agentbox.manifest import (
    parse_manifest,
    validate_manifest,
    generate_default_manifest,
    generate_eval_template,
    AgentManifest,
    MANIFEST_FILENAME,
)


VALID_YAML = """\
agent:
  name: test-agent
  version: 0.1.0
  description: A test agent
  model: claude-sonnet-4-20250514
  framework: anthropic
  memory: conversation
  eval_suite: ./evals/test_suite.yaml

  tools:
    - name: search
      type: function

  guardrails:
    - no-pii: SSN
"""


@pytest.fixture
def agent_dir(tmp_path):
    manifest = tmp_path / MANIFEST_FILENAME
    manifest.write_text(VALID_YAML)
    return tmp_path


def test_parse_manifest_returns_agent_manifest(agent_dir):
    m = parse_manifest(str(agent_dir))
    assert isinstance(m, AgentManifest)
    assert m.name == "test-agent"
    assert m.version == "0.1.0"
    assert m.model == "claude-sonnet-4-20250514"
    assert m.framework == "anthropic"
    assert m.memory == "conversation"


def test_parse_manifest_tools(agent_dir):
    m = parse_manifest(str(agent_dir))
    assert len(m.tools) == 1
    assert m.tools[0].name == "search"
    assert m.tools[0].type == "function"


def test_parse_manifest_guardrails(agent_dir):
    m = parse_manifest(str(agent_dir))
    assert len(m.guardrails) == 1
    assert m.guardrails[0].name == "no-pii"


def test_parse_manifest_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        parse_manifest(str(tmp_path))


def test_parse_manifest_invalid_yaml(tmp_path):
    (tmp_path / MANIFEST_FILENAME).write_text("name: [invalid: yaml: here")
    with pytest.raises(Exception):
        parse_manifest(str(tmp_path))


def test_validate_manifest_clean(agent_dir):
    m = parse_manifest(str(agent_dir))
    issues = validate_manifest(m)
    errors = [i for i in issues if i.startswith("ERROR")]
    assert len(errors) == 0


def test_validate_manifest_missing_name():
    m = AgentManifest(name="", version="1.0.0", model="gpt-4o", framework="openai")
    issues = validate_manifest(m)
    assert any("name" in i.lower() for i in issues)


def test_validate_manifest_missing_model():
    m = AgentManifest(name="test", version="1.0.0", model="", framework="openai")
    issues = validate_manifest(m)
    assert any("model" in i.lower() for i in issues)


def test_validate_manifest_no_system_prompt_is_warning():
    m = AgentManifest(name="test", version="1.0.0", model="gpt-4o", framework="openai")
    issues = validate_manifest(m)
    assert any("system prompt" in i.lower() for i in issues)


def test_generate_default_manifest_is_valid_yaml():
    import yaml
    content = generate_default_manifest("hello-agent")
    parsed = yaml.safe_load(content)
    agent = parsed.get("agent", parsed)  # handle both flat and nested
    assert agent.get("name") == "hello-agent" or parsed.get("name") == "hello-agent"


def test_generate_eval_template_is_valid_yaml():
    import yaml
    content = generate_eval_template()
    parsed = yaml.safe_load(content)
    assert parsed is not None
    assert isinstance(parsed, dict)
