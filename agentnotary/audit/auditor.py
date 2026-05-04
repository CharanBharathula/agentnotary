"""
agentnotary.audit.auditor
=========================
Forensic session auditor.

Given a recorded session JSON, produce a structured + human-readable audit:
  - timeline of actions
  - tools called, with frequency and total cost
  - guardrails triggered
  - PII detected (post-hoc scan of stored content)
  - cost breakdown per step
  - red flags (cost spikes, repeated identical tool calls, errors followed by
    recovery, guardrail bypass attempts)
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Optional

from agentnotary.guard import pii as pii_mod
from agentnotary.recorder import load_session


@dataclass
class AuditFinding:
    severity: str       # info | warn | high | critical
    code: str
    title: str
    detail: str
    step_indices: list = field(default_factory=list)


@dataclass
class AuditReport:
    session_id: str
    agent_name: str
    agent_version: str
    model: str
    started_at: str
    ended_at: Optional[str]
    status: str
    duration_seconds: float
    total_cost_usd: float
    total_tokens: int

    action_count: int
    llm_call_count: int
    tool_call_count: int
    guardrail_event_count: int
    error_count: int

    tools_called: dict = field(default_factory=dict)        # name -> count
    tool_costs: dict = field(default_factory=dict)          # name -> usd (estimated)
    cost_per_step: list = field(default_factory=list)       # cumulative
    findings: list = field(default_factory=list)            # list[AuditFinding]


# ── Helper analyses ────────────────────────────────────────────────────


def _scan_pii_in_session(session: dict) -> list:
    """Scan all stored prompt/response content for PII. Returns findings."""
    findings = []
    for i, action in enumerate(session.get("actions", []), start=1):
        content = action.get("content") or {}
        for field_name in ("prompt_preview", "response_preview", "input", "output"):
            text = content.get(field_name, "")
            if not isinstance(text, str) or not text:
                continue
            matches = pii_mod.detect(text)
            if matches:
                kinds = sorted({m.pattern for m in matches})
                findings.append(AuditFinding(
                    severity="high" if "SSN" in kinds or "CREDIT_CARD" in kinds else "warn",
                    code=f"AUDIT-PII-{','.join(kinds)}",
                    title=f"PII present in action #{i} ({field_name})",
                    detail=(f"Action {i} ({action.get('action_type', '?')}) contains "
                            f"{', '.join(kinds)} pattern(s). Consider enabling pii.action=block."),
                    step_indices=[i],
                ))
    return findings


def _detect_repeat_loops(actions: list) -> list:
    """Flag identical tool/LLM calls happening 5+ times consecutively."""
    findings = []
    if len(actions) < 5:
        return findings

    fingerprints = []
    for a in actions:
        atype = a.get("action_type", "")
        content = a.get("content") or {}
        if atype == "tool_call":
            fingerprints.append(("tool", content.get("tool"), str(content.get("args"))[:80]))
        elif atype == "llm_call":
            fingerprints.append(("llm", "-", content.get("prompt_preview", "")[:80]))
        else:
            fingerprints.append(("other", atype, ""))

    # Find runs of identical fingerprints of length >= 5
    i = 0
    while i < len(fingerprints):
        j = i + 1
        while j < len(fingerprints) and fingerprints[j] == fingerprints[i]:
            j += 1
        run_len = j - i
        if run_len >= 5 and fingerprints[i][0] in ("tool", "llm"):
            findings.append(AuditFinding(
                severity="high",
                code="AUDIT-REPEAT-LOOP",
                title=f"Repeat-loop detected: {run_len} identical {fingerprints[i][0]} calls",
                detail=f"Steps {i+1}-{j}: identical {fingerprints[i][0]} call repeated.",
                step_indices=list(range(i + 1, j + 1)),
            ))
        i = j

    return findings


def _detect_cost_spikes(actions: list) -> list:
    """Flag steps that consumed disproportionate cost."""
    findings = []
    costs = [(i + 1, a.get("cost_usd") or 0)
              for i, a in enumerate(actions) if a.get("cost_usd")]
    if not costs:
        return findings
    total = sum(c for _, c in costs)
    if total <= 0:
        return findings
    for idx, c in costs:
        share = c / total
        if share > 0.5 and total > 0.05:
            findings.append(AuditFinding(
                severity="warn",
                code="AUDIT-COST-SPIKE",
                title=f"Step {idx} consumed {int(share*100)}% of session cost",
                detail=f"${c:.4f} of ${total:.4f} total. Investigate prompt size or tool result.",
                step_indices=[idx],
            ))
    return findings


def _summarize_tools(actions: list) -> tuple:
    counts: Counter = Counter()
    costs: dict = {}
    for a in actions:
        if a.get("action_type") != "tool_call":
            continue
        content = a.get("content") or {}
        name = content.get("tool", "?")
        counts[name] += 1
        costs[name] = costs.get(name, 0.0) + (a.get("cost_usd") or 0.0)
    return dict(counts), costs


# ── Public API ─────────────────────────────────────────────────────────


def audit_session(session_id: str, base_dir: str = ".") -> AuditReport:
    """Audit a recorded session by id (full or prefix). Returns AuditReport."""
    session = load_session(session_id, base_dir)
    actions = session.get("actions", [])

    tools_called, tool_costs = _summarize_tools(actions)

    cost_running = 0.0
    cost_per_step: list = []
    for a in actions:
        cost_running += (a.get("cost_usd") or 0.0)
        cost_per_step.append(round(cost_running, 6))

    findings: list[AuditFinding] = []
    findings.extend(_scan_pii_in_session(session))
    findings.extend(_detect_repeat_loops(actions))
    findings.extend(_detect_cost_spikes(actions))

    # Derived stats
    llm_calls = sum(1 for a in actions if a.get("action_type") == "llm_call")
    tool_calls = sum(1 for a in actions if a.get("action_type") == "tool_call")
    guard_events = sum(1 for a in actions if a.get("action_type") == "guardrail_triggered")
    errors = sum(1 for a in actions if a.get("action_type") == "error")

    if guard_events:
        findings.append(AuditFinding(
            severity="info",
            code="AUDIT-GUARDRAIL-FIRED",
            title=f"{guard_events} guardrail event(s) recorded",
            detail="Guardrails fired during this session — review manifest tuning.",
        ))
    if errors:
        findings.append(AuditFinding(
            severity="warn",
            code="AUDIT-ERRORS",
            title=f"{errors} error(s) recorded",
            detail="Investigate error context in the session log.",
        ))
    if not actions:
        findings.append(AuditFinding(
            severity="info",
            code="AUDIT-EMPTY",
            title="Session has zero recorded actions",
            detail="Did SessionRecorder receive any record_*() calls?",
        ))

    return AuditReport(
        session_id=session.get("session_id", session_id),
        agent_name=session.get("agent_name", "?"),
        agent_version=session.get("agent_version", "?"),
        model=session.get("model", "?"),
        started_at=session.get("started_at", ""),
        ended_at=session.get("ended_at"),
        status=session.get("status", "?"),
        duration_seconds=float(session.get("duration_seconds") or 0),
        total_cost_usd=float(session.get("total_cost_usd") or 0),
        total_tokens=int(session.get("total_tokens") or 0),
        action_count=len(actions),
        llm_call_count=llm_calls,
        tool_call_count=tool_calls,
        guardrail_event_count=guard_events,
        error_count=errors,
        tools_called=tools_called,
        tool_costs={k: round(v, 6) for k, v in tool_costs.items()},
        cost_per_step=cost_per_step,
        findings=findings,
    )
