"""Tests for the session recorder / flight recorder."""

from pathlib import Path

import pytest

from agentnotary.recorder import SessionRecorder, list_sessions, load_session


@pytest.fixture
def agent_dir(tmp_path):
    (tmp_path / ".agentnotary" / "sessions").mkdir(parents=True)
    return tmp_path


def make_recorder(agent_dir, name="test-agent", version="0.1.0", model="claude-sonnet-4-20250514"):
    return SessionRecorder(name, version, model, base_dir=str(agent_dir))


def test_recorder_creates_session_file(agent_dir):
    recorder = make_recorder(agent_dir)
    recorder.complete(status="completed")
    session_files = list(Path(agent_dir / ".agentnotary" / "sessions").glob("*.json"))
    assert len(session_files) == 1


def test_recorder_session_id_is_unique(agent_dir):
    r1 = make_recorder(agent_dir)
    r2 = make_recorder(agent_dir)
    assert r1.session.session_id != r2.session.session_id


def test_recorder_exposes_session_id(agent_dir):
    recorder = make_recorder(agent_dir)
    assert hasattr(recorder, "session")
    assert recorder.session.session_id


def test_recorder_stores_llm_call(agent_dir):
    recorder = make_recorder(agent_dir)
    recorder.record_llm_call(
        prompt="Hello",
        response="Hi there!",
        duration_ms=300,
        cost_usd=0.001,
        tokens=30,
    )
    recorder.complete("completed")

    sessions = list_sessions(str(agent_dir))
    assert len(sessions) == 1
    data = load_session(sessions[0]["session_id"], str(agent_dir))
    llm_actions = [a for a in data["actions"] if a["action_type"] == "llm_call"]
    assert len(llm_actions) == 1
    assert llm_actions[0]["duration_ms"] == 300


def test_recorder_stores_tool_call(agent_dir):
    recorder = make_recorder(agent_dir)
    recorder.record_tool_call("search_kb", {"query": "refund policy"}, "Found policy doc")
    recorder.complete("completed")

    data = load_session(recorder.session.session_id, str(agent_dir))
    tool_actions = [a for a in data["actions"] if a["action_type"] == "tool_call"]
    assert len(tool_actions) == 1


def test_recorder_stores_decision(agent_dir):
    recorder = make_recorder(agent_dir)
    recorder.record_decision("escalate", reasoning="User frustrated")
    recorder.complete("completed")

    data = load_session(recorder.session.session_id, str(agent_dir))
    decisions = [a for a in data["actions"] if a["action_type"] == "decision"]
    assert len(decisions) == 1


def test_recorder_stores_error(agent_dir):
    recorder = make_recorder(agent_dir)
    recorder.record_error("TimeoutError", context="LLM call timed out")
    recorder.complete("error")

    data = load_session(recorder.session.session_id, str(agent_dir))
    errors = [a for a in data["actions"] if a["action_type"] == "error"]
    assert len(errors) == 1


def test_recorder_aggregates_cost(agent_dir):
    recorder = make_recorder(agent_dir)
    recorder.record_llm_call("p1", "r1", 100, cost_usd=0.01, tokens=10)
    recorder.record_llm_call("p2", "r2", 200, cost_usd=0.02, tokens=20)
    recorder.complete("completed")

    data = load_session(recorder.session.session_id, str(agent_dir))
    assert abs(data["total_cost_usd"] - 0.03) < 1e-9


def test_list_sessions_returns_metadata(agent_dir):
    recorder = make_recorder(agent_dir, name="agent-x", version="1.0.0")
    recorder.complete("completed")

    sessions = list_sessions(str(agent_dir))
    assert len(sessions) == 1
    s = sessions[0]
    assert s["agent_name"] == "agent-x"
    assert "session_id" in s
    assert "started_at" in s


def test_list_sessions_empty(tmp_path):
    (tmp_path / ".agentnotary" / "sessions").mkdir(parents=True)
    assert list_sessions(str(tmp_path)) == []


def test_load_session_not_found_raises(agent_dir):
    with pytest.raises(FileNotFoundError):
        load_session("nonexistent-id-xyz", str(agent_dir))


def test_recorder_guardrail_event(agent_dir):
    recorder = make_recorder(agent_dir)
    recorder.record_guardrail("no-pii", triggered_by="SSN detected", action_taken="blocked")
    recorder.complete("completed")

    data = load_session(recorder.session.session_id, str(agent_dir))
    guardrail_events = [a for a in data["actions"] if a["action_type"] == "guardrail_triggered"]
    assert len(guardrail_events) == 1


def test_recorder_complete_returns_session(agent_dir):
    recorder = make_recorder(agent_dir)
    session = recorder.complete("completed")
    assert session.status == "completed"
    assert session.ended_at is not None
