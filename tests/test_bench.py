"""Tests for cross-model bench (Pareto comparison)."""

from pathlib import Path

import pytest

from agentnotary.bench import BenchResult, ModelBenchResult, pareto_chart, run_bench
from agentnotary.bench.runner import _pareto_frontier, _parse_model_arg

FIXTURE = Path(__file__).parent / "fixtures" / "agentnotary_v02.yaml"


@pytest.fixture
def bench_dir(tmp_path):
    (tmp_path / "agentnotary.yaml").write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "evals").mkdir()
    (tmp_path / "evals" / "test_suite.yaml").write_text(
        "evals:\n"
        "  - { name: greet, input: 'Hello', expected_behavior: 'greets' }\n"
        "  - { name: ask, input: 'What can you do?', expected_behavior: 'lists capabilities' }\n",
        encoding="utf-8",
    )
    return tmp_path


# ── parse_model_arg ────────────────────────────────────────────────────


def test_parse_model_arg_explicit():
    assert _parse_model_arg("anthropic/claude-sonnet-4") == ("anthropic", "claude-sonnet-4")
    assert _parse_model_arg("openai/gpt-4o") == ("openai", "gpt-4o")


def test_parse_model_arg_inferred():
    assert _parse_model_arg("claude-sonnet-4-5-20251022")[0] == "anthropic"
    assert _parse_model_arg("gpt-4o")[0] == "openai"
    assert _parse_model_arg("gemini-2.5-flash")[0] == "google"
    assert _parse_model_arg("unknown-model")[0] == "unknown"


# ── run_bench (dry-run) ────────────────────────────────────────────────


def test_run_bench_default_models(bench_dir):
    result = run_bench(str(bench_dir), dry_run=True)
    assert isinstance(result, BenchResult)
    assert len(result.models) == 4  # the default lineup
    assert result.dry_run is True
    assert result.n_cases == 2


def test_run_bench_explicit_models(bench_dir):
    result = run_bench(str(bench_dir),
                        models=["anthropic/claude-sonnet-4", "openai/gpt-4o"],
                        dry_run=True)
    assert len(result.models) == 2


def test_run_bench_results_are_modelbenchresult(bench_dir):
    result = run_bench(str(bench_dir), models=["openai/gpt-4o-mini"], dry_run=True)
    r = result.models[0]
    assert isinstance(r, ModelBenchResult)
    assert r.provider == "openai"
    assert r.model == "gpt-4o-mini"
    assert r.cases_run == 2


def test_run_bench_unknown_model_pricing_marked(bench_dir):
    result = run_bench(str(bench_dir),
                        models=["unknown/some-model-not-in-table"],
                        dry_run=True)
    r = result.models[0]
    assert r.pricing_known is False
    assert "UNKNOWN PRICING" in r.notes


def test_run_bench_missing_eval_suite_raises(tmp_path):
    (tmp_path / "agentnotary.yaml").write_text(FIXTURE.read_text(encoding="utf-8"),
                                                 encoding="utf-8")
    # No evals/ dir
    with pytest.raises(FileNotFoundError):
        run_bench(str(tmp_path), dry_run=True)


# ── Pareto frontier ────────────────────────────────────────────────────


def _make_model(provider, name, pass_rate, cost):
    return ModelBenchResult(
        provider=provider, model=name, pass_rate=pass_rate, total_cost_usd=cost,
        avg_latency_ms=1000, cases_run=10, cases_passed=int(pass_rate * 10),
        cases_failed=10 - int(pass_rate * 10), cases_errored=0,
    )


def test_pareto_frontier_excludes_dominated():
    a = _make_model("openai", "gpt-4o-mini", 0.7, 0.001)   # cheap + decent
    b = _make_model("openai", "gpt-4o", 0.9, 0.01)          # expensive + best
    c = _make_model("openai", "gpt-3.5", 0.6, 0.005)        # dominated by a
    frontier = _pareto_frontier([a, b, c])
    refs = [(r.provider, r.model) for r in frontier]
    assert ("openai", "gpt-4o-mini") in refs
    assert ("openai", "gpt-4o") in refs
    assert ("openai", "gpt-3.5") not in refs


def test_pareto_frontier_singleton():
    only = _make_model("anthropic", "claude-sonnet-4", 0.8, 0.005)
    frontier = _pareto_frontier([only])
    assert len(frontier) == 1


# ── Chart rendering ────────────────────────────────────────────────────


def test_pareto_chart_renders(bench_dir):
    result = run_bench(str(bench_dir), models=["openai/gpt-4o", "openai/gpt-4o-mini"],
                        dry_run=True)
    chart = pareto_chart(result)
    assert "Pareto" in chart
    assert "Models tested" in chart
    assert "openai/gpt-4o" in chart


def test_pareto_chart_empty():
    result = BenchResult(eval_path="x", n_cases=0, models=[], pareto_frontier=[])
    assert pareto_chart(result) == "(no results)"
