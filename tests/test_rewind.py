"""Tests for time-travel session debugging (rewind)."""

from pathlib import Path

import pytest

from agentnotary.recorder import SessionRecorder
from agentnotary.rewind import diff_step, list_steps, rewind_session

FIXTURE = Path(__file__).parent / "fixtures" / "agentnotary_v02.yaml"


@pytest.fixture
def session_dir(tmp_path):
    """Set up an agent dir with a recorded session."""
    (tmp_path / "agentnotary.yaml").write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / ".agentnotary" / "sessions").mkdir(parents=True)

    rec = SessionRecorder(
        agent_name="support-agent",
        agent_version="0.3.1",
        model="claude-sonnet-4-5-20251022",
        base_dir=str(tmp_path),
    )
    rec.record_llm_call("Hello", "Hi! How can I help?", duration_ms=300, cost_usd=0.001, tokens=20)
    rec.record_tool_call("search_kb", {"q": "refund policy"}, "policy doc")
    rec.record_decision("escalate", reasoning="user is upset")
    rec.record_llm_call("Are you sure?", "Yes, escalating now.", duration_ms=200, cost_usd=0.0008, tokens=15)
    rec.complete("completed")

    return tmp_path, rec.session.session_id


# ── list_steps ─────────────────────────────────────────────────────────


def test_list_steps_returns_all_actions(session_dir):
    base_dir, sid = session_dir
    steps = list_steps(sid, str(base_dir))
    assert len(steps) == 4
    assert [s.action_type for s in steps] == ["llm_call", "tool_call", "decision", "llm_call"]


def test_list_steps_indices_start_at_one(session_dir):
    base_dir, sid = session_dir
    steps = list_steps(sid, str(base_dir))
    assert steps[0].index == 1
    assert steps[-1].index == len(steps)


def test_list_steps_summaries_are_human_readable(session_dir):
    base_dir, sid = session_dir
    steps = list_steps(sid, str(base_dir))
    assert "LLM:" in steps[0].summary
    assert "TOOL[search_kb]" in steps[1].summary
    assert "DECIDE" in steps[2].summary


# ── diff_step ──────────────────────────────────────────────────────────


def test_diff_step_returns_action_content(session_dir):
    base_dir, sid = session_dir
    action = diff_step(sid, str(base_dir), 1)
    assert action["action_type"] == "llm_call"


def test_diff_step_out_of_range_raises(session_dir):
    base_dir, sid = session_dir
    with pytest.raises(IndexError):
        diff_step(sid, str(base_dir), 99)


# ── rewind_session ─────────────────────────────────────────────────────


def test_rewind_no_fork_returns_full_session(session_dir):
    base_dir, sid = session_dir
    result = rewind_session(sid, str(base_dir))
    assert result.fork_step is None
    assert len(result.steps) == 4
    # All steps not simulated
    assert all(not s.is_simulated for s in result.steps)


def test_rewind_with_fork_marks_simulated_steps(session_dir):
    base_dir, sid = session_dir
    result = rewind_session(sid, str(base_dir), fork_step=2)
    assert result.fork_step == 2
    # Steps 1, 2 not simulated; steps 3, 4 are
    assert result.steps[0].is_simulated is False
    assert result.steps[1].is_simulated is False
    assert result.steps[1].is_fork_point is True
    assert result.steps[2].is_simulated is True
    assert result.steps[3].is_simulated is True


def test_rewind_with_edit_truncates_after_fork(session_dir):
    base_dir, sid = session_dir
    result = rewind_session(sid, str(base_dir),
                              fork_step=1, edit_prompt="Hello, but this time differently")
    # Steps 1 fork, plus a "trajectory diverged" stub — steps 2/3/4 are gone
    assert len(result.steps) == 2
    assert result.steps[0].is_fork_point is True
    assert result.steps[1].action_type == "rewind_truncated"
    assert "diverged" in result.steps[1].summary.lower()


def test_rewind_edit_with_no_api_uses_simulated_response(session_dir):
    base_dir, sid = session_dir
    # No API key in env in tests → falls back to simulated response
    result = rewind_session(sid, str(base_dir), fork_step=1, edit_prompt="Try this")
    assert result.used_live_llm is False
    fork = result.steps[0]
    content = fork.raw.get("content", {})
    assert content.get("__rewind_edited") is True
    # Simulated response is in the response_preview
    assert "REWIND-SIMULATED" in content.get("response_preview", "") or \
           "stand-in" in content.get("response_preview", "").lower()


def test_rewind_invalid_fork_step_raises(session_dir):
    base_dir, sid = session_dir
    with pytest.raises(IndexError):
        rewind_session(sid, str(base_dir), fork_step=99, edit_prompt="x")


def test_rewind_session_not_found(session_dir):
    base_dir, _ = session_dir
    with pytest.raises(FileNotFoundError):
        rewind_session("no-such-id-here", str(base_dir))


def test_rewind_notes_explain_what_happened(session_dir):
    base_dir, sid = session_dir
    result = rewind_session(sid, str(base_dir), fork_step=2, edit_prompt="What if I asked X?")
    # At least one note explaining the divergence
    assert result.notes
    assert any("Diverged" in n for n in result.notes)
