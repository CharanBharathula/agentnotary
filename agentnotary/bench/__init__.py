"""
agentnotary.bench
==============
Cross-model Pareto comparison for AI agents.

Runs the agent's eval suite against N models in parallel, projects the
cost-vs-accuracy frontier, and emits an ASCII Pareto chart plus structured
JSON for slide decks.

Public API:
    run_bench(base_dir, models, eval_path) -> BenchResult
    pareto_chart(result) -> str
"""

from agentnotary.bench.runner import (
    BenchResult,
    ModelBenchResult,
    pareto_chart,
    run_bench,
)

__all__ = ["BenchResult", "ModelBenchResult", "pareto_chart", "run_bench"]
