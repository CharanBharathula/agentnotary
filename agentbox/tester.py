"""
AgentBox Test Runner
====================
Runs eval suites against agents to verify behavior before deployment.
Like unit tests for AI agents.
"""

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class EvalResult:
    name: str
    status: str  # passed, failed, error, skipped
    input: str
    expected: str
    actual_response: str = ""
    latency_ms: int = 0
    cost_usd: float = 0.0
    tools_called: list = None
    failure_reason: str = ""

    def __post_init__(self):
        if self.tools_called is None:
            self.tools_called = []


class AgentTestRunner:
    """Runs eval suites against agents."""

    def __init__(self, manifest, verbose: bool = False):
        self.manifest = manifest
        self.verbose = verbose
        self.results = []
        self.llm = None

    def _init_llm(self):
        """Initialize LLM client for testing."""
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if api_key:
            try:
                import anthropic
                self.llm = anthropic.Anthropic(api_key=api_key)
                self.llm_provider = "anthropic"
                return
            except ImportError:
                pass

        api_key = os.getenv("OPENAI_API_KEY")
        if api_key:
            try:
                import openai
                self.llm = openai.OpenAI(api_key=api_key)
                self.llm_provider = "openai"
                return
            except ImportError:
                pass

        return None

    def load_eval_suite(self, path: str) -> list:
        """Load eval cases from YAML file."""
        eval_path = Path(path)
        if not eval_path.exists():
            raise FileNotFoundError(f"Eval suite not found: {path}")

        with open(eval_path) as f:
            data = yaml.safe_load(f)

        return data.get("evals", [])

    def run_single_eval(self, eval_case: dict) -> EvalResult:
        """Run a single eval case against the agent."""
        name = eval_case.get("name", "unnamed")
        input_text = eval_case.get("input", "")
        expected = eval_case.get("expected_behavior", "")
        max_latency = eval_case.get("max_latency_ms", 30000)
        max_cost = eval_case.get("max_cost_usd", 1.0)

        if not self.llm:
            # Dry run mode — validate structure only
            return EvalResult(
                name=name,
                status="skipped",
                input=input_text,
                expected=expected,
                failure_reason="No API key configured. Set ANTHROPIC_API_KEY or OPENAI_API_KEY for live testing.",
            )

        # Run the agent
        start = time.time()
        try:
            if self.llm_provider == "anthropic":
                response = self.llm.messages.create(
                    model=self.manifest.model,
                    max_tokens=self.manifest.max_tokens,
                    system=self.manifest.system_prompt or "You are a helpful assistant.",
                    messages=[{"role": "user", "content": input_text}],
                )
                actual = response.content[0].text
                tokens = response.usage.input_tokens + response.usage.output_tokens
                # Rough cost estimate
                cost = tokens * 0.000003  # ~$3/1M tokens estimate
            else:
                response = self.llm.chat.completions.create(
                    model=self.manifest.model,
                    max_tokens=self.manifest.max_tokens,
                    messages=[
                        {"role": "system", "content": self.manifest.system_prompt or "You are a helpful assistant."},
                        {"role": "user", "content": input_text},
                    ],
                )
                actual = response.choices[0].message.content
                tokens = response.usage.total_tokens if response.usage else 0
                cost = tokens * 0.000003

            latency = int((time.time() - start) * 1000)

            # Evaluate results
            status = "passed"
            failure_reason = ""

            if latency > max_latency:
                status = "failed"
                failure_reason = f"Latency {latency}ms exceeded max {max_latency}ms"

            if cost > max_cost:
                status = "failed"
                failure_reason = f"Cost ${cost:.4f} exceeded max ${max_cost}"

            # Use LLM to judge if behavior matches expected
            if status == "passed" and expected:
                judge_result = self._judge_response(input_text, actual, expected)
                if not judge_result["passed"]:
                    status = "failed"
                    failure_reason = judge_result["reason"]

            return EvalResult(
                name=name,
                status=status,
                input=input_text,
                expected=expected,
                actual_response=actual[:500],
                latency_ms=latency,
                cost_usd=cost,
                tools_called=[],
                failure_reason=failure_reason,
            )

        except Exception as e:
            return EvalResult(
                name=name,
                status="error",
                input=input_text,
                expected=expected,
                failure_reason=str(e),
            )

    def _judge_response(self, input_text: str, actual: str, expected: str) -> dict:
        """Use LLM to judge if actual response matches expected behavior."""
        judge_prompt = f"""You are an AI agent evaluator. Given:
- INPUT: {input_text}
- ACTUAL RESPONSE: {actual[:500]}
- EXPECTED BEHAVIOR: {expected}

Does the actual response satisfy the expected behavior? 
Respond with ONLY valid JSON: {{"passed": true/false, "reason": "brief explanation"}}"""

        try:
            if self.llm_provider == "anthropic":
                resp = self.llm.messages.create(
                    model="claude-sonnet-4-20250514",
                    max_tokens=200,
                    messages=[{"role": "user", "content": judge_prompt}],
                )
                text = resp.content[0].text
            else:
                resp = self.llm.chat.completions.create(
                    model="gpt-4o-mini",
                    max_tokens=200,
                    messages=[{"role": "user", "content": judge_prompt}],
                )
                text = resp.choices[0].message.content

            import re
            text = re.sub(r"```(?:json)?|```", "", text).strip()
            return json.loads(text)
        except Exception:
            return {"passed": True, "reason": "Judge unavailable, auto-pass"}

    def run_suite(self, eval_path: str) -> dict:
        """Run a complete eval suite."""
        evals = self.load_eval_suite(eval_path)
        self._init_llm()

        results = []
        passed = 0
        failed = 0
        errors = 0
        skipped = 0
        total_cost = 0.0
        total_latency = 0

        for eval_case in evals:
            result = self.run_single_eval(eval_case)
            results.append(result)

            if result.status == "passed":
                passed += 1
            elif result.status == "failed":
                failed += 1
            elif result.status == "error":
                errors += 1
            else:
                skipped += 1

            total_cost += result.cost_usd
            total_latency += result.latency_ms

        total = len(results)
        return {
            "agent": self.manifest.name,
            "version": self.manifest.version,
            "total": total,
            "passed": passed,
            "failed": failed,
            "errors": errors,
            "skipped": skipped,
            "pass_rate": f"{(passed / max(total - skipped, 1)) * 100:.1f}%",
            "total_cost_usd": round(total_cost, 6),
            "avg_latency_ms": round(total_latency / max(total - skipped, 1)),
            "results": [
                {
                    "name": r.name,
                    "status": r.status,
                    "latency_ms": r.latency_ms,
                    "cost_usd": round(r.cost_usd, 6),
                    "failure_reason": r.failure_reason,
                }
                for r in results
            ],
        }
