"""Tests for the forensic session auditor."""


import pytest

from agentnotary.audit import audit_session
from agentnotary.recorder import SessionRecorder


def _record(tmp_path, *, with_loop=False, with_pii=False, with_cost_spike=False):
    (tmp_path / ".agentnotary" / "sessions").mkdir(parents=True)
    rec = SessionRecorder(
        agent_name="forensic-agent", agent_version="1.0.0",
        model="claude-sonnet-4-5-20251022", base_dir=str(tmp_path),
    )

    rec.record_llm_call("Hello", "Hi!", duration_ms=300, cost_usd=0.001, tokens=20)

    if with_pii:
        rec.record_llm_call(
            "Customer email is alice@example.com and SSN 123-45-6789",
            "I see, looking up the account.",
            duration_ms=250, cost_usd=0.001, tokens=30,
        )

    if with_loop:
        for _ in range(6):
            rec.record_tool_call("identical_search", {"q": "same query"}, "result")

    rec.record_tool_call("search_kb", {"q": "refund"}, "policy doc")

    if with_cost_spike:
        rec.record_llm_call("expensive query", "...", duration_ms=2000, cost_usd=0.50, tokens=500)

    rec.record_decision("escalate", reasoning="user upset")
    rec.complete("completed")
    return rec.session.session_id


@pytest.fixture
def session_dir(tmp_path):
    sid = _record(tmp_path)
    return tmp_path, sid


def test_audit_returns_report(session_dir):
    base, sid = session_dir
    report = audit_session(sid, str(base))
    assert report.session_id
    assert report.agent_name == "forensic-agent"
    assert report.action_count > 0


def test_audit_counts_action_types(session_dir):
    base, sid = session_dir
    report = audit_session(sid, str(base))
    assert report.llm_call_count == 1
    assert report.tool_call_count >= 1
    assert report.action_count == report.llm_call_count + report.tool_call_count + 1  # +decision


def test_audit_summarizes_tools(session_dir):
    base, sid = session_dir
    report = audit_session(sid, str(base))
    assert "search_kb" in report.tools_called
    assert report.tools_called["search_kb"] == 1


def test_audit_detects_pii_in_session(tmp_path):
    sid = _record(tmp_path, with_pii=True)
    report = audit_session(sid, str(tmp_path))
    pii_findings = [f for f in report.findings if "PII" in f.code]
    assert pii_findings
    # SSN/CC should escalate to "high"
    high = [f for f in pii_findings if f.severity == "high"]
    assert high


def test_audit_detects_repeat_loops(tmp_path):
    sid = _record(tmp_path, with_loop=True)
    report = audit_session(sid, str(tmp_path))
    loop_findings = [f for f in report.findings if f.code == "AUDIT-REPEAT-LOOP"]
    assert loop_findings
    assert loop_findings[0].severity == "high"
    assert len(loop_findings[0].step_indices) >= 5


def test_audit_detects_cost_spikes(tmp_path):
    sid = _record(tmp_path, with_cost_spike=True)
    report = audit_session(sid, str(tmp_path))
    spike = [f for f in report.findings if f.code == "AUDIT-COST-SPIKE"]
    assert spike


def test_audit_session_not_found(tmp_path):
    (tmp_path / ".agentnotary" / "sessions").mkdir(parents=True)
    with pytest.raises(FileNotFoundError):
        audit_session("does-not-exist", str(tmp_path))


def test_audit_cost_per_step_is_cumulative(session_dir):
    base, sid = session_dir
    report = audit_session(sid, str(base))
    assert len(report.cost_per_step) == report.action_count
    # Should be monotonically non-decreasing
    for i in range(1, len(report.cost_per_step)):
        assert report.cost_per_step[i] >= report.cost_per_step[i - 1]


def test_audit_clean_session_has_no_findings(session_dir):
    base, sid = session_dir
    report = audit_session(sid, str(base))
    # Plain session — no PII, no loops, no spikes
    pii = [f for f in report.findings if "PII" in f.code]
    loops = [f for f in report.findings if f.code == "AUDIT-REPEAT-LOOP"]
    spikes = [f for f in report.findings if f.code == "AUDIT-COST-SPIKE"]
    assert not pii
    assert not loops
    assert not spikes
