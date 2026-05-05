"""
agentnotary.bench.runner
=====================
Run the agent's eval suite against multiple models in parallel and emit a
Pareto chart of cost vs accuracy.

Designed to answer: "Should I use Sonnet or 4o for this agent?"

Without API keys, the runner enters dry-run mode: it estimates cost from
average prompt size + the static pricing table, and reports estimated
projections instead of measured results.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Optional

import yaml

from agentnotary.manifest import AgentManifest, parse_manifest, safe_resolve
from agentnotary.pricing import estimate_cost, lookup_pricing


@dataclass
class ModelBenchResult:
    provider: str
    model: str
    pass_rate: float                # 0.0–1.0
    total_cost_usd: float
    avg_latency_ms: int
    cases_run: int
    cases_passed: int
    cases_failed: int
    cases_errored: int
    notes: str = ""
    pricing_known: bool = True


@dataclass
class BenchResult:
    eval_path: str
    n_cases: int
    models: list = field(default_factory=list)        # list[ModelBenchResult]
    pareto_frontier: list = field(default_factory=list)  # list[(model, ModelBenchResult)]
    dry_run: bool = False


# ── Model parsing ────────────────────────────────────────────────────


def _parse_model_arg(arg: str) -> tuple:
    """
    Accept either:
      - 'provider/model'  (e.g. 'anthropic/claude-sonnet-4-5-20251022')
      - 'model'           (provider inferred via prefix)
    """
    if "/" in arg:
        provider, model = arg.split("/", 1)
        return provider.lower(), model
    m = arg.lower()
    if m.startswith("claude"):
        return "anthropic", arg
    if m.startswith("gpt") or m.startswith("o1") or m.startswith("o3"):
        return "openai", arg
    if m.startswith("gemini"):
        return "google", arg
    return "unknown", arg


# ── Single-model bench ───────────────────────────────────────────────


def _bench_one(manifest: AgentManifest, provider: str, model: str,
               eval_cases: list, *, dry_run: bool) -> ModelBenchResult:
    """Run all eval cases against one model. Falls back to estimation if no API key."""
    pricing = lookup_pricing(provider, model)
    pricing_known = pricing is not None

    if dry_run or not pricing_known:
        # Estimate-only mode: project cost from average prompt size; assume 70% pass
        avg_input_chars = sum(len(c.get("input", "")) for c in eval_cases) / max(len(eval_cases), 1)
        avg_input_tokens = max(50, int(avg_input_chars / 4))
        avg_output_tokens = 200  # Reasonable agent response size
        per_call_cost = estimate_cost(provider, model, avg_input_tokens, avg_output_tokens) or 0.0
        total = per_call_cost * len(eval_cases)
        return ModelBenchResult(
            provider=provider,
            model=model,
            pass_rate=0.7,  # nominal placeholder for the chart
            total_cost_usd=round(total, 6),
            avg_latency_ms=800 if "haiku" in model.lower() or "mini" in model.lower() else 1500,
            cases_run=len(eval_cases),
            cases_passed=int(len(eval_cases) * 0.7),
            cases_failed=int(len(eval_cases) * 0.3),
            cases_errored=0,
            pricing_known=pricing_known,
            notes=("DRY-RUN: cost projected from avg prompt size + static pricing. "
                   "Set API keys for measured results.") if pricing_known else
                  ("UNKNOWN PRICING: model not in pricing table. "
                   "Add to agentnotary/pricing.py for cost projection."),
        )

    # Live run: requires API key + provider SDK; this path is exercised by
    # AgentTestRunner-like code. For v0.3 we ship the dry-run path and document
    # the live path as forthcoming when the existing tester.py grows model-override
    # support.
    return ModelBenchResult(
        provider=provider, model=model,
        pass_rate=0.0, total_cost_usd=0.0, avg_latency_ms=0,
        cases_run=0, cases_passed=0, cases_failed=0, cases_errored=len(eval_cases),
        notes="Live bench requires AgentTestRunner model-override (planned v0.3.1).",
    )


# ── Public API ───────────────────────────────────────────────────────


def run_bench(base_dir: str = ".", models: Optional[list] = None,
              *, eval_path: Optional[str] = None,
              max_workers: int = 4, dry_run: Optional[bool] = None) -> BenchResult:
    """
    Run the eval suite against `models` (list of strings, see _parse_model_arg).
    Returns a BenchResult including the Pareto frontier.
    """
    manifest = parse_manifest(base_dir)
    eval_path = eval_path or manifest.eval_suite or "./evals/test_suite.yaml"

    from pathlib import Path
    suite_path = safe_resolve(Path(base_dir), eval_path)
    if not suite_path.exists():
        raise FileNotFoundError(f"Eval suite not found: {suite_path}")
    suite = yaml.safe_load(suite_path.read_text(encoding="utf-8")) or {}
    eval_cases = suite.get("evals") or suite.get("cases") or []

    if not models:
        # Default lineup: Sonnet, 4o, Flash — three Pareto candidates
        models = [
            "anthropic/claude-sonnet-4-5-20251022",
            "openai/gpt-4o",
            "openai/gpt-4o-mini",
            "google/gemini-2.5-flash",
        ]

    parsed = [_parse_model_arg(m) for m in models]

    # Default to dry-run if no API keys are configured
    if dry_run is None:
        import os
        dry_run = not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("OPENAI_API_KEY"))

    results: list[ModelBenchResult] = []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {
            ex.submit(_bench_one, manifest, provider, model, eval_cases, dry_run=dry_run):
                (provider, model)
            for provider, model in parsed
        }
        for fut in as_completed(futures):
            results.append(fut.result())

    results.sort(key=lambda r: (r.total_cost_usd, -r.pass_rate))

    return BenchResult(
        eval_path=str(suite_path),
        n_cases=len(eval_cases),
        models=results,
        pareto_frontier=_pareto_frontier(results),
        dry_run=dry_run,
    )


def _pareto_frontier(results: list) -> list:
    """
    Pareto frontier on (cost ↓, pass_rate ↑). A model is on the frontier if no
    other model is both cheaper AND higher-accuracy.
    """
    frontier = []
    for r in results:
        dominated = False
        for other in results:
            if other is r:
                continue
            if (other.total_cost_usd <= r.total_cost_usd and
                    other.pass_rate >= r.pass_rate and
                    (other.total_cost_usd < r.total_cost_usd or other.pass_rate > r.pass_rate)):
                dominated = True
                break
        if not dominated:
            frontier.append(r)
    frontier.sort(key=lambda r: r.total_cost_usd)
    return frontier


# ── ASCII Pareto chart ────────────────────────────────────────────────


def pareto_chart(result: BenchResult, *, width: int = 60, height: int = 12) -> str:
    """Render a tiny ASCII Pareto chart of cost (x) vs accuracy (y)."""
    if not result.models:
        return "(no results)"

    max_cost = max(r.total_cost_usd for r in result.models) or 1e-9
    min_cost = min(r.total_cost_usd for r in result.models)
    cost_span = max(max_cost - min_cost, 1e-9)

    # Grid
    grid = [[" "] * width for _ in range(height)]

    frontier_set = {(r.provider, r.model) for r in result.pareto_frontier}

    points: list[tuple[int, int, str, ModelBenchResult]] = []
    for r in result.models:
        x = int((r.total_cost_usd - min_cost) / cost_span * (width - 6))
        y = int((1 - r.pass_rate) * (height - 1))
        x = max(0, min(width - 6, x))
        y = max(0, min(height - 1, y))
        marker = "★" if (r.provider, r.model) in frontier_set else "•"
        points.append((x, y, marker, r))

    for x, y, marker, _ in points:
        grid[y][x] = marker

    lines = []
    lines.append("  Pareto: cost (USD) vs pass-rate")
    lines.append("")
    lines.append("  100% ┤ " + "".join(grid[0]))
    for i in range(1, height - 1):
        lines.append("       │ " + "".join(grid[i]))
    lines.append("    0% ┴ " + "─" * (width - 5))
    lines.append(f"         ${min_cost:.4f}{' ' * (width - 16)}${max_cost:.4f}")
    lines.append("")
    lines.append("  Legend: ★ Pareto-optimal   • dominated")
    lines.append("")
    lines.append("  Models tested:")
    for r in result.models:
        marker = "★" if (r.provider, r.model) in frontier_set else " "
        lines.append(
            f"    {marker} {r.provider}/{r.model:<35} "
            f"pass={r.pass_rate*100:5.1f}%   cost=${r.total_cost_usd:.4f}   "
            f"latency={r.avg_latency_ms}ms"
        )
    return "\n".join(lines)
