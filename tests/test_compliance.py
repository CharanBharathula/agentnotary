"""Tests for the compliance generator and risk classifier."""

import json
from pathlib import Path

import pytest

from agentbox.compliance import check, classify_risk, generate
from agentbox.compliance.classifier import HIGH_RISK_KEYWORDS
from agentbox.manifest import parse_manifest

FIXTURE = Path(__file__).parent / "fixtures" / "agentbox_v02.yaml"


@pytest.fixture
def agent_dir(tmp_path):
    (tmp_path / "agentbox.yaml").write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "evals").mkdir()
    (tmp_path / "evals" / "test_suite.yaml").write_text("evals: []\n", encoding="utf-8")
    (tmp_path / ".agentbox" / "sessions").mkdir(parents=True)
    return tmp_path


# ── Risk classifier ─────────────────────────────────────────────────────


def test_classifier_detects_external_consumers(agent_dir):
    m = parse_manifest(str(agent_dir))
    risk = classify_risk(m)
    # Fixture has affected_users=external_consumers; should be limited
    assert risk.risk_class == "limited"
    assert any("TRANSPARENCY" in fr.rule.code for fr in risk.fired_rules)


def test_classifier_high_risk_for_payment_tools(tmp_path):
    yaml_text = """
apiVersion: agentbox/v0.2
agent:
  name: pay-agent
  version: 1.0.0
  framework: anthropic
  model:
    provider: anthropic
    name: claude-sonnet-4-5
  tools:
    - name: process_payment
      type: api
      endpoint: https://api.stripe.com/v1/charges
  compliance:
    risk_class: minimal
    affected_users: external_consumers
    intended_purpose: "Charges customer credit cards for purchases"
"""
    (tmp_path / "agentbox.yaml").write_text(yaml_text, encoding="utf-8")
    m = parse_manifest(str(tmp_path))
    risk = classify_risk(m)
    assert risk.risk_class == "high"
    assert any(fr.rule.risk_class == "high" for fr in risk.fired_rules)


def test_classifier_minimal_for_internal_only(tmp_path):
    yaml_text = """
apiVersion: agentbox/v0.2
agent:
  name: internal-bot
  version: 1.0.0
  framework: anthropic
  model: { provider: anthropic, name: claude-haiku-4 }
  compliance:
    risk_class: minimal
    affected_users: internal
    intended_purpose: "Internal log summarization"
"""
    (tmp_path / "agentbox.yaml").write_text(yaml_text, encoding="utf-8")
    m = parse_manifest(str(tmp_path))
    risk = classify_risk(m)
    assert risk.risk_class == "minimal"


def test_classifier_high_risk_for_minors(tmp_path):
    yaml_text = """
apiVersion: agentbox/v0.2
agent:
  name: tutor-bot
  version: 1.0.0
  framework: anthropic
  model: { provider: anthropic, name: claude-sonnet-4 }
  compliance:
    risk_class: limited
    affected_users: minors
    intended_purpose: "Tutoring assistant for K-12 students"
"""
    (tmp_path / "agentbox.yaml").write_text(yaml_text, encoding="utf-8")
    m = parse_manifest(str(tmp_path))
    risk = classify_risk(m)
    assert risk.risk_class == "high"
    assert any("VULNERABLE" in fr.rule.code for fr in risk.fired_rules)


def test_classifier_cites_firing_rules(agent_dir):
    m = parse_manifest(str(agent_dir))
    risk = classify_risk(m)
    assert risk.fired_rules
    for fr in risk.fired_rules:
        assert fr.rule.code
        assert fr.matched


def test_high_risk_keyword_categories_complete():
    expected = {"biometric", "critical_infrastructure", "education", "employment",
                "essential_services", "law_enforcement", "migration", "justice",
                "healthcare", "payment"}
    assert expected.issubset(set(HIGH_RISK_KEYWORDS.keys()))


# ── check() — CI mode ───────────────────────────────────────────────────


def test_check_passes_on_complete_manifest(agent_dir):
    m = parse_manifest(str(agent_dir))
    issues = check(m)
    errors = [i for i in issues if i.severity == "error"]
    assert errors == []


def test_check_flags_missing_intended_purpose(tmp_path):
    yaml_text = """
apiVersion: agentbox/v0.2
agent:
  name: nopurpose
  version: 1.0.0
  framework: anthropic
  model: { provider: anthropic, name: claude-sonnet-4 }
  system_prompt: "..."
  compliance:
    risk_class: minimal
    affected_users: internal
"""
    (tmp_path / "agentbox.yaml").write_text(yaml_text, encoding="utf-8")
    m = parse_manifest(str(tmp_path))
    issues = check(m)
    assert any(i.severity == "error" and "intended_purpose" in i.field for i in issues)


def test_check_no_compliance_block_is_error(tmp_path):
    yaml_text = """
agent:
  name: bare
  version: 1.0.0
  model: claude-sonnet-4
  framework: anthropic
"""
    (tmp_path / "agentbox.yaml").write_text(yaml_text, encoding="utf-8")
    m = parse_manifest(str(tmp_path))
    issues = check(m)
    assert any(i.severity == "error" for i in issues)


# ── generate() — end-to-end ─────────────────────────────────────────────


def test_generate_writes_markdown_and_json(agent_dir, tmp_path):
    out = tmp_path / "out"
    result = generate(str(agent_dir), "eu-ai-act", str(out))
    assert any(f.name.endswith(".md") for f in result.files_written)
    assert any(f.name.endswith(".json") for f in result.files_written)


def test_generate_markdown_contains_disclaimer(agent_dir, tmp_path):
    out = tmp_path / "out"
    generate(str(agent_dir), "eu-ai-act", str(out), format="markdown")
    md = (out / "eu_ai_act_annex_iv.md").read_text(encoding="utf-8")
    assert "NOT legal advice" in md
    assert "Annex IV" in md


def test_generate_markdown_contains_all_sections(agent_dir, tmp_path):
    out = tmp_path / "out"
    generate(str(agent_dir), "eu-ai-act", str(out), format="markdown")
    md = (out / "eu_ai_act_annex_iv.md").read_text(encoding="utf-8")
    for section in ["1. General description",
                    "2. Detailed system description",
                    "3. Monitoring",
                    "4. Risk management",
                    "5. Data and data governance",
                    "6. Human oversight",
                    "7. Accuracy",
                    "8. Lifecycle changes",
                    "9. Compliance with harmonized standards"]:
        assert section in md, f"Section missing: {section}"


def test_generate_json_is_valid_and_structured(agent_dir, tmp_path):
    out = tmp_path / "out"
    generate(str(agent_dir), "eu-ai-act", str(out), format="json")
    payload = json.loads((out / "eu_ai_act_annex_iv.json").read_text(encoding="utf-8"))
    assert payload["standard"] == "eu-ai-act-annex-iv"
    assert "risk_assessment" in payload
    assert payload["risk_assessment"]["classified_as"] in {"minimal", "limited", "high", "unacceptable"}
    assert payload["agent"]["name"] == "support-agent"


def test_generate_unknown_standard_raises(agent_dir, tmp_path):
    with pytest.raises(ValueError, match="Unsupported standard"):
        generate(str(agent_dir), "made-up", str(tmp_path / "out"))
