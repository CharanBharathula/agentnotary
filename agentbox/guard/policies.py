"""
agentbox.guard.policies
=======================
Policy engine that evaluates a manifest's GuardrailSpec against intercepted
LLM/tool calls. Stateful (tracks accumulated cost, iteration count, rate).

The engine is provider-agnostic: it consumes already-parsed call metadata
(tool names, prompt text, projected cost) and emits decisions.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

from agentbox.guard import pii as pii_mod
from agentbox.manifest import AgentManifest, GuardrailSpec


@dataclass
class PolicyViolation:
    rule: str  # e.g. "cost.max_usd_per_session"
    detail: str
    action: str  # block | warn | log


@dataclass
class PolicyDecision:
    allowed: bool
    violations: list = field(default_factory=list)
    redacted_prompt: Optional[str] = None  # set if PII redaction modified the prompt
    redacted_tools: Optional[list] = None  # set if tool list was filtered

    def block_violation(self) -> Optional[PolicyViolation]:
        for v in self.violations:
            if v.action == "block":
                return v
        return None


@dataclass
class CallMeta:
    """Pre-flight metadata the proxy extracts from an intercepted request."""
    provider: str
    model: str
    prompt_text: str  # concatenated user/system content for PII scan
    tools_requested: list = field(default_factory=list)  # tool names from request body
    projected_input_tokens: int = 0


class PolicyEngine:
    """
    Stateful per-session policy engine.

    Usage:
        engine = PolicyEngine(manifest)
        decision = engine.pre_flight(call_meta)
        if not decision.allowed: ...reject...
        engine.post_flight(actual_input_tokens, actual_output_tokens, actual_cost_usd)
    """

    def __init__(self, manifest: AgentManifest):
        self.manifest = manifest
        self.spec: GuardrailSpec = manifest.guardrail_spec or GuardrailSpec()

        # Stateful counters
        self.session_cost_usd: float = 0.0
        self.llm_call_count: int = 0
        self.tool_call_count: int = 0
        self.session_call_count: int = 0
        self._call_timestamps: list = []  # for rate limiting
        self.session_started: float = time.time()

    # ── Pre-flight ────────────────────────────────────────────────

    def pre_flight(self, call: CallMeta, projected_cost_usd: Optional[float] = None) -> PolicyDecision:
        violations: list[PolicyViolation] = []
        redacted_prompt = None
        redacted_tools = None

        # 1. Iterations
        if self.spec.iterations.max_llm_calls is not None:
            if self.llm_call_count >= self.spec.iterations.max_llm_calls:
                violations.append(PolicyViolation(
                    rule="iterations.max_llm_calls",
                    detail=(f"LLM call cap of {self.spec.iterations.max_llm_calls} reached "
                            f"(call #{self.llm_call_count + 1} would exceed it)"),
                    action=self.spec.iterations.action,
                ))

        # 2. Cost (pre-flight projection)
        if projected_cost_usd is not None and self.spec.cost.max_usd_per_call is not None:
            if projected_cost_usd > self.spec.cost.max_usd_per_call:
                violations.append(PolicyViolation(
                    rule="cost.max_usd_per_call",
                    detail=(f"Projected call cost ${projected_cost_usd:.4f} exceeds per-call cap "
                            f"${self.spec.cost.max_usd_per_call:.4f}"),
                    action=self.spec.cost.action,
                ))
        if projected_cost_usd is not None and self.spec.cost.max_usd_per_session is not None:
            projected_total = self.session_cost_usd + projected_cost_usd
            if projected_total > self.spec.cost.max_usd_per_session:
                violations.append(PolicyViolation(
                    rule="cost.max_usd_per_session",
                    detail=(f"Projected session cost ${projected_total:.4f} would exceed "
                            f"session cap ${self.spec.cost.max_usd_per_session:.4f}"),
                    action=self.spec.cost.action,
                ))

        # 3. Tool allow/denylist
        if call.tools_requested:
            allowlist = self.spec.tools.allowlist
            denylist = self.spec.tools.denylist
            disallowed = []
            for tname in call.tools_requested:
                if denylist and tname in denylist:
                    disallowed.append(tname)
                elif allowlist and tname not in allowlist:
                    disallowed.append(tname)
            if disallowed:
                violations.append(PolicyViolation(
                    rule="tools.allowlist",
                    detail=(f"Tools not permitted: {', '.join(disallowed)}. "
                            f"Allowlist: {allowlist or '<none>'}"),
                    action=self.spec.tools.action,
                ))

        # 4. PII (inbound — what the agent sends)
        if self.spec.pii.direction in ("inbound", "both"):
            patterns = self.spec.pii.patterns or list(pii_mod.PATTERNS.keys())
            matches = pii_mod.detect(call.prompt_text, patterns)
            if matches:
                if self.spec.pii.action == "redact":
                    redacted_prompt = pii_mod.redact(call.prompt_text, matches)
                    # Redaction is not a violation; it modifies the request
                else:
                    violations.append(PolicyViolation(
                        rule="pii.inbound",
                        detail=(f"Outbound PII detected: "
                                f"{', '.join(sorted({m.pattern for m in matches}))}"),
                        action=self.spec.pii.action,
                    ))

        # 5. Content size
        if self.spec.content.max_input_tokens is not None:
            if call.projected_input_tokens > self.spec.content.max_input_tokens:
                violations.append(PolicyViolation(
                    rule="content.max_input_tokens",
                    detail=(f"Input tokens {call.projected_input_tokens} exceed cap "
                            f"{self.spec.content.max_input_tokens}"),
                    action=self.spec.content.action,
                ))

        # 6. Rate
        now = time.time()
        # Drop timestamps older than 60s
        self._call_timestamps = [t for t in self._call_timestamps if now - t < 60]
        if self.spec.rate.max_calls_per_minute is not None:
            if len(self._call_timestamps) >= self.spec.rate.max_calls_per_minute:
                violations.append(PolicyViolation(
                    rule="rate.max_calls_per_minute",
                    detail=(f"Rate limit: {len(self._call_timestamps)} calls in last minute "
                            f">= cap {self.spec.rate.max_calls_per_minute}"),
                    action=self.spec.rate.action,
                ))
        if self.spec.rate.max_calls_per_session is not None:
            if self.session_call_count >= self.spec.rate.max_calls_per_session:
                violations.append(PolicyViolation(
                    rule="rate.max_calls_per_session",
                    detail=(f"Session call cap reached: {self.session_call_count} >= "
                            f"{self.spec.rate.max_calls_per_session}"),
                    action=self.spec.rate.action,
                ))

        # An "allowed" decision means no `block` violations fired.
        any_block = any(v.action == "block" for v in violations)
        return PolicyDecision(
            allowed=not any_block,
            violations=violations,
            redacted_prompt=redacted_prompt,
            redacted_tools=redacted_tools,
        )

    # ── Post-flight ───────────────────────────────────────────────

    def post_flight(self, *, input_tokens: int, output_tokens: int,
                    cost_usd: Optional[float], is_tool_call: bool = False) -> None:
        """Record actuals after a successful provider call."""
        self.llm_call_count += 1
        self.session_call_count += 1
        self._call_timestamps.append(time.time())
        if cost_usd is not None:
            self.session_cost_usd += cost_usd
        if is_tool_call:
            self.tool_call_count += 1

    def post_flight_response_pii(self, response_text: str) -> Optional[PolicyViolation]:
        """Scan the model's response for outbound PII leak."""
        if self.spec.pii.direction not in ("outbound", "both"):
            return None
        if self.spec.pii.action == "redact":
            return None  # We don't redact responses in v0.2 (would corrupt structured outputs)
        patterns = self.spec.pii.patterns or list(pii_mod.PATTERNS.keys())
        matches = pii_mod.detect(response_text, patterns)
        if matches:
            return PolicyViolation(
                rule="pii.outbound",
                detail=(f"Response contains PII: "
                        f"{', '.join(sorted({m.pattern for m in matches}))}"),
                action=self.spec.pii.action,
            )
        return None

    # ── Summary ───────────────────────────────────────────────────

    def summary(self) -> dict:
        return {
            "session_cost_usd": round(self.session_cost_usd, 6),
            "llm_calls": self.llm_call_count,
            "tool_calls": self.tool_call_count,
            "session_seconds": round(time.time() - self.session_started, 2),
        }
