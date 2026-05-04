"""Tests for AI-BOM generation (CycloneDX + SPDX)."""

import json
from pathlib import Path

import pytest

from agentnotary.bom import SUPPORTED_BOM_FORMATS, generate_bom, write_bom

FIXTURE = Path(__file__).parent / "fixtures" / "agentnotary_v02.yaml"


@pytest.fixture
def agent_dir(tmp_path):
    (tmp_path / "agentnotary.yaml").write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "system.md").write_text("You are the agent.", encoding="utf-8")
    (tmp_path / "evals").mkdir()
    (tmp_path / "evals" / "test_suite.yaml").write_text("evals: []\n", encoding="utf-8")
    (tmp_path / ".agentnotary" / "sessions").mkdir(parents=True)
    return tmp_path


def test_supported_formats():
    assert "cyclonedx" in SUPPORTED_BOM_FORMATS
    assert "spdx" in SUPPORTED_BOM_FORMATS


def test_unknown_format_raises(agent_dir):
    with pytest.raises(ValueError, match="Unsupported BOM format"):
        generate_bom(str(agent_dir), format="unknown")


# ── CycloneDX ──────────────────────────────────────────────────────────


def test_cyclonedx_has_required_fields(agent_dir):
    bom = generate_bom(str(agent_dir), format="cyclonedx")
    assert bom["bomFormat"] == "CycloneDX"
    assert bom["specVersion"] == "1.6"
    assert bom["serialNumber"].startswith("urn:uuid:")
    assert bom["version"] == 1
    assert "metadata" in bom
    assert "components" in bom


def test_cyclonedx_metadata_contains_agent(agent_dir):
    bom = generate_bom(str(agent_dir), format="cyclonedx")
    component = bom["metadata"]["component"]
    assert component["name"] == "support-agent"
    assert component["version"] == "0.3.1"
    assert component["type"] == "application"


def test_cyclonedx_includes_model_component(agent_dir):
    bom = generate_bom(str(agent_dir), format="cyclonedx")
    model_components = [
        c for c in bom["components"]
        if c.get("type") == "machine-learning-model"
    ]
    assert len(model_components) == 1
    m = model_components[0]
    assert m["name"] == "claude-sonnet-4-5-20251022"
    assert "purl" in m
    assert m["purl"].startswith("pkg:ai-model/")


def test_cyclonedx_with_seal_includes_prompts_and_tools(agent_dir):
    from agentnotary.seal import seal_agent, write_lock
    write_lock(seal_agent(str(agent_dir)), str(agent_dir))

    bom = generate_bom(str(agent_dir), format="cyclonedx")
    types = [c.get("type") for c in bom["components"]]
    # Should have model + prompt(s) + tool(s) + dataset(s)
    assert "machine-learning-model" in types
    assert "data" in types
    # Prompts have agentnotary:type property
    prompt_components = [
        c for c in bom["components"]
        if any(p.get("name") == "agentnotary:type" and p.get("value") == "prompt"
               for p in c.get("properties", []))
    ]
    assert len(prompt_components) >= 1


def test_cyclonedx_dependencies_section(agent_dir):
    bom = generate_bom(str(agent_dir), format="cyclonedx")
    assert "dependencies" in bom
    deps = bom["dependencies"]
    assert len(deps) >= 1
    main_ref = deps[0]
    assert "ref" in main_ref
    assert "dependsOn" in main_ref


# ── SPDX ───────────────────────────────────────────────────────────────


def test_spdx_required_fields(agent_dir):
    bom = generate_bom(str(agent_dir), format="spdx")
    assert bom["spdxVersion"] == "SPDX-2.3"
    assert bom["dataLicense"] == "CC0-1.0"
    assert bom["SPDXID"] == "SPDXRef-DOCUMENT"
    assert bom["name"].endswith("sbom")
    assert "packages" in bom
    assert "relationships" in bom


def test_spdx_creation_info_lists_agentnotary(agent_dir):
    bom = generate_bom(str(agent_dir), format="spdx")
    creators = bom["creationInfo"]["creators"]
    assert any("AgentNotary" in c for c in creators)


def test_spdx_packages_include_main_agent(agent_dir):
    bom = generate_bom(str(agent_dir), format="spdx")
    names = [p["name"] for p in bom["packages"]]
    assert "support-agent" in names


def test_spdx_relationships_describe_main(agent_dir):
    bom = generate_bom(str(agent_dir), format="spdx")
    rels = bom["relationships"]
    describes = [r for r in rels if r["relationshipType"] == "DESCRIBES"]
    assert len(describes) == 1


# ── write_bom ──────────────────────────────────────────────────────────


def test_write_bom_default_filenames(agent_dir, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # Copy manifest to current dir for write_bom
    (tmp_path / "agentnotary.yaml").write_text(
        (agent_dir / "agentnotary.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    cdx_path = write_bom(format="cyclonedx")
    spdx_path = write_bom(format="spdx")
    assert cdx_path.name == "agent.sbom.cdx.json"
    assert spdx_path.name == "agent.sbom.spdx.json"
    # Must be valid JSON
    json.loads(cdx_path.read_text(encoding="utf-8"))
    json.loads(spdx_path.read_text(encoding="utf-8"))


def test_write_bom_custom_path(agent_dir):
    custom = agent_dir / "my-bom.json"
    path = write_bom(str(agent_dir), format="cyclonedx", output_path=str(custom))
    assert path == custom
    assert custom.exists()
