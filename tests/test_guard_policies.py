"""Tests for the guard policy engine and PII detector."""

from pathlib import Path

import pytest

from agentnotary.guard import pii
from agentnotary.guard.policies import CallMeta, PolicyEngine
from agentnotary.manifest import parse_manifest

FIXTURE = Path(__file__).parent / "fixtures" / "agentnotary_v02.yaml"


@pytest.fixture
def manifest(tmp_path):
    (tmp_path / "agentnotary.yaml").write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    return parse_manifest(str(tmp_path))


# ── PII detector ────────────────────────────────────────────────────────


def test_pii_detects_email():
    matches = pii.detect("Contact me at jane.doe@example.com tomorrow.")
    assert any(m.pattern == "EMAIL" for m in matches)


def test_pii_detects_ssn():
    matches = pii.detect("My SSN is 123-45-6789.")
    assert any(m.pattern == "SSN" for m in matches)


def test_pii_detects_credit_card():
    matches = pii.detect("Card: 4111-1111-1111-1111")
    assert any(m.pattern == "CREDIT_CARD" for m in matches)


def test_pii_clean_text():
    assert pii.detect("This is a clean prompt with no PII.") == []


def test_pii_redact_replaces_match():
    text = "Email: foo@bar.com. SSN: 123-45-6789."
    matches = pii.detect(text)
    redacted = pii.redact(text, matches)
    assert "foo@bar.com" not in redacted
    assert "123-45-6789" not in redacted
    assert "[REDACTED-EMAIL]" in redacted
    assert "[REDACTED-SSN]" in redacted


def test_pii_filter_by_pattern():
    matches = pii.detect("Email a@b.com SSN 123-45-6789", patterns=["SSN"])
    assert all(m.pattern == "SSN" for m in matches)


# ── Policy engine ───────────────────────────────────────────────────────


def test_engine_blocks_disallowed_tool(manifest):
    engine = PolicyEngine(manifest)
    decision = engine.pre_flight(CallMeta(
        provider="anthropic",
        model="claude-sonnet-4-5-20251022",
        prompt_text="hello",
        tools_requested=["disallowed_tool"],
    ))
    assert not decision.allowed
    assert any("tools.allowlist" in v.rule for v in decision.violations)


def test_engine_allows_listed_tool(manifest):
    engine = PolicyEngine(manifest)
    decision = engine.pre_flight(CallMeta(
        provider="anthropic",
        model="claude-sonnet-4-5-20251022",
        prompt_text="hello",
        tools_requested=["search_kb"],
    ))
    assert decision.allowed


def test_engine_redacts_pii_when_action_redact(manifest):
    engine = PolicyEngine(manifest)
    decision = engine.pre_flight(CallMeta(
        provider="anthropic",
        model="claude-sonnet-4-5-20251022",
        prompt_text="My email is jane@example.com",
        tools_requested=[],
    ))
    # PII action is "redact" in the fixture; should NOT block, but redacted_prompt should be set
    assert decision.allowed
    assert decision.redacted_prompt is not None
    assert "jane@example.com" not in decision.redacted_prompt
    assert "[REDACTED-EMAIL]" in decision.redacted_prompt


def test_engine_blocks_when_iterations_exceeded(manifest):
    engine = PolicyEngine(manifest)
    # Push counter past the cap
    engine.llm_call_count = manifest.guardrail_spec.iterations.max_llm_calls
    decision = engine.pre_flight(CallMeta(
        provider="anthropic",
        model="claude-sonnet-4-5-20251022",
        prompt_text="hi",
        tools_requested=["search_kb"],
    ))
    assert not decision.allowed
    assert any("iterations.max_llm_calls" in v.rule for v in decision.violations)


def test_engine_blocks_when_session_cost_exceeded(manifest):
    engine = PolicyEngine(manifest)
    # Already spent; another call would push past $0.50
    engine.session_cost_usd = 0.49
    decision = engine.pre_flight(
        CallMeta(provider="anthropic", model="claude-sonnet-4-5-20251022",
                  prompt_text="hi", tools_requested=["search_kb"]),
        projected_cost_usd=0.05,
    )
    assert not decision.allowed
    assert any("cost.max_usd_per_session" in v.rule for v in decision.violations)


def test_engine_blocks_when_call_cost_exceeded(manifest):
    engine = PolicyEngine(manifest)
    decision = engine.pre_flight(
        CallMeta(provider="anthropic", model="claude-sonnet-4-5-20251022",
                  prompt_text="hi", tools_requested=["search_kb"]),
        projected_cost_usd=0.50,  # cap is $0.10 per-call
    )
    assert not decision.allowed
    assert any("cost.max_usd_per_call" in v.rule for v in decision.violations)


def test_engine_post_flight_accumulates_cost(manifest):
    engine = PolicyEngine(manifest)
    engine.post_flight(input_tokens=100, output_tokens=50, cost_usd=0.05)
    engine.post_flight(input_tokens=200, output_tokens=100, cost_usd=0.10)
    summary = engine.summary()
    assert abs(summary["session_cost_usd"] - 0.15) < 1e-9
    assert summary["llm_calls"] == 2


def test_engine_no_guardrail_spec_allows_all(tmp_path):
    """With no typed guardrails, the engine permits everything but still tracks usage."""
    (tmp_path / "agentnotary.yaml").write_text(
        "agent:\n  name: open-agent\n  version: 0.1.0\n  model: claude-sonnet-4\n  framework: anthropic\n",
        encoding="utf-8",
    )
    m = parse_manifest(str(tmp_path))
    engine = PolicyEngine(m)
    decision = engine.pre_flight(CallMeta(
        provider="anthropic", model="claude-sonnet-4",
        prompt_text="anything", tools_requested=["any_tool"],
    ))
    assert decision.allowed


def test_engine_summary_keys(manifest):
    engine = PolicyEngine(manifest)
    s = engine.summary()
    assert set(s.keys()) >= {"session_cost_usd", "llm_calls", "tool_calls", "session_seconds"}
