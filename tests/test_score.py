"""Tests for the governance score + badge."""

import json
from pathlib import Path

import pytest

from agentnotary.score import score
from agentnotary.score.scorer import badge_color, badge_url

FIXTURE = Path(__file__).parent / "fixtures" / "agentnotary_v02.yaml"


@pytest.fixture
def scored_dir(tmp_path):
    (tmp_path / "agentnotary.yaml").write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "evals").mkdir()
    (tmp_path / "evals" / "test_suite.yaml").write_text(
        "evals:\n" + "".join(
            f"  - {{ name: c{i}, input: 'q{i}', expected_behavior: 'b{i}' }}\n"
            for i in range(6)
        ),
        encoding="utf-8",
    )
    return tmp_path


def test_score_returns_report(scored_dir):
    report = score(str(scored_dir))
    assert 0 <= report.score <= 100
    assert report.grade in {"A", "B", "C", "D", "F"}
    assert report.summary
    assert report.items


def test_score_no_manifest_returns_zero(tmp_path):
    report = score(str(tmp_path))
    assert report.score == 0
    assert report.grade == "F"
    assert any(i.severity == "fail" for i in report.items)


def test_score_with_seal_present_increases(scored_dir):
    """Sealing should add ≥20 points to the score."""
    pre = score(str(scored_dir)).score
    from agentnotary.seal import seal_agent, write_lock
    write_lock(seal_agent(str(scored_dir)), str(scored_dir))
    post = score(str(scored_dir)).score
    assert post > pre
    assert post - pre >= 8  # at least the seal points (20 ideal, 8 if drift detected)


def test_score_dimensions_covered(scored_dir):
    report = score(str(scored_dir))
    dims = {i.dimension for i in report.items}
    expected = {"seal", "guardrails", "attack", "compliance", "evals", "reproducibility", "ops"}
    assert expected.issubset(dims)


def test_score_actionable_items_have_fix_hints(scored_dir):
    report = score(str(scored_dir))
    actionable = [i for i in report.items if i.severity in ("warn", "fail")]
    # Most actionable items should have a fix_hint
    with_hints = [i for i in actionable if i.fix_hint]
    assert len(with_hints) >= len(actionable) // 2


def test_score_perfect_grade_thresholds():
    from agentnotary.score.scorer import _grade
    assert _grade(95) == "A"
    assert _grade(80) == "B"
    assert _grade(65) == "C"
    assert _grade(45) == "D"
    assert _grade(30) == "F"


# ── Badge ──────────────────────────────────────────────────────────────


def test_badge_url_format():
    url = badge_url(75)
    assert url.startswith("https://img.shields.io/badge/")
    assert "agentnotary" in url
    assert "75" in url


def test_badge_color_thresholds():
    assert badge_color(95) == "brightgreen"
    assert badge_color(80) == "green"
    assert badge_color(65) == "yellowgreen"
    assert badge_color(50) == "yellow"
    assert badge_color(25) == "orange"
    assert badge_color(10) == "red"


def test_score_attack_consumed_from_last_attack_json(scored_dir):
    """If .agentnotary/last_attack.json exists, score should reflect it."""
    state = scored_dir / ".agentnotary"
    state.mkdir(exist_ok=True)
    (state / "last_attack.json").write_text(
        json.dumps({"vulnerability_rate": 0.0, "successful_attacks": 0, "total_attacks": 11}),
        encoding="utf-8",
    )
    report = score(str(scored_dir))
    attack_items = report.by_dimension("attack")
    assert attack_items
    earned = sum(i.points_earned for i in attack_items)
    assert earned == 15  # full marks for 0% vuln rate
