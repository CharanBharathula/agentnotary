"""Tests for the v0.2 typed manifest schema."""

from pathlib import Path

import pytest

from agentbox.manifest import (
    API_VERSION_V02,
    ComplianceMeta,
    GuardrailSpec,
    ModelSpec,
    parse_manifest,
)

FIXTURE = Path(__file__).parent / "fixtures" / "agentbox_v02.yaml"


@pytest.fixture
def v02_dir(tmp_path):
    (tmp_path / "agentbox.yaml").write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    return tmp_path


def test_parses_v02_apiversion(v02_dir):
    m = parse_manifest(str(v02_dir))
    assert m.api_version == API_VERSION_V02
    assert m.is_v02 is True


def test_parses_typed_model_spec(v02_dir):
    m = parse_manifest(str(v02_dir))
    assert isinstance(m.model_spec, ModelSpec)
    assert m.model_spec.provider == "anthropic"
    assert m.model_spec.name == "claude-sonnet-4-5-20251022"
    assert m.model_spec.pinned_version == "claude-sonnet-4-5-20251022"
    assert m.model_spec.temperature == 0.2


def test_effective_model_uses_typed_spec(v02_dir):
    m = parse_manifest(str(v02_dir))
    assert m.effective_model == "claude-sonnet-4-5-20251022"
    assert m.effective_provider == "anthropic"


def test_parses_typed_guardrails(v02_dir):
    m = parse_manifest(str(v02_dir))
    assert isinstance(m.guardrail_spec, GuardrailSpec)
    assert m.guardrail_spec.cost.max_usd_per_session == 0.50
    assert m.guardrail_spec.cost.max_usd_per_call == 0.10
    assert m.guardrail_spec.cost.action == "block"
    assert m.guardrail_spec.iterations.max_llm_calls == 25
    assert "search_kb" in m.guardrail_spec.tools.allowlist
    assert "create_ticket" in m.guardrail_spec.tools.allowlist
    assert "create_ticket" in m.guardrail_spec.tools.require_approval
    assert "SSN" in m.guardrail_spec.pii.patterns
    assert m.guardrail_spec.pii.action == "redact"
    assert m.guardrail_spec.rate.max_calls_per_minute == 60


def test_parses_compliance_metadata(v02_dir):
    m = parse_manifest(str(v02_dir))
    assert isinstance(m.compliance, ComplianceMeta)
    assert m.compliance.risk_class == "limited"
    assert m.compliance.affected_users == "external_consumers"
    assert m.compliance.human_oversight == "review_required"
    assert "Tier-1 customer support" in m.compliance.intended_purpose
    assert "medical advice" in m.compliance.out_of_scope
    assert m.compliance.data_handling.processes_pii is True
    assert "email" in m.compliance.data_handling.pii_categories
    assert m.compliance.data_handling.retention_days == 30


def test_parses_entry_point(v02_dir):
    m = parse_manifest(str(v02_dir))
    assert m.entry_point is not None
    assert m.entry_point.command == "python -m app.support_agent"
    assert "ANTHROPIC_API_KEY" in m.entry_point.env_vars


def test_tools_have_typed_fields(v02_dir):
    m = parse_manifest(str(v02_dir))
    by_name = {t.name: t for t in m.tools}
    assert by_name["search_kb"].type == "function"
    assert by_name["search_kb"].module == "app.tools:search_kb"
    assert by_name["create_ticket"].type == "api"
    assert by_name["create_ticket"].endpoint == "https://api.helpdesk.example.com/tickets"
    assert by_name["create_ticket"].auth == "HELPDESK_TOKEN"


def test_v01_manifest_still_parses(tmp_path):
    """Backwards compatibility: existing v0.1 form continues to work."""
    (tmp_path / "agentbox.yaml").write_text(
        "agent:\n"
        "  name: legacy-agent\n"
        "  version: 0.1.0\n"
        "  model: claude-sonnet-4-20250514\n"
        "  framework: anthropic\n"
        "  guardrails:\n"
        "    - max_spend_per_run: $1.00\n",
        encoding="utf-8",
    )
    m = parse_manifest(str(tmp_path))
    assert m.is_v02 is False
    assert m.name == "legacy-agent"
    assert m.model_spec is None
    assert m.guardrail_spec is None
    # Legacy guardrails populate the legacy list
    assert len(m.guardrails) == 1


def test_to_dict_includes_v02_fields(v02_dir):
    m = parse_manifest(str(v02_dir))
    d = m.to_dict()
    assert d["api_version"] == API_VERSION_V02
    assert d["provider"] == "anthropic"
    assert d["compliance_risk"] == "limited"
