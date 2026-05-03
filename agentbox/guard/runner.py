"""
agentbox.guard.runner
=====================
Orchestrates `agentbox guard run -- <command>`:
    1. Parse the manifest and start a local proxy in a background asyncio loop.
    2. Set provider base URLs to point at the proxy.
    3. Spawn the user's agent command as a subprocess with the modified env.
    4. Stream subprocess stdout/stderr back to the user.
    5. On subprocess exit (or guard kill), tear down the proxy and write
       the session log via the existing SessionRecorder.

Returns a GuardResult with exit_code, summary stats, and violations.
"""

from __future__ import annotations

import asyncio
import os
import sys
from dataclasses import dataclass, field
from typing import Optional

from agentbox.guard.policies import PolicyEngine, PolicyViolation
from agentbox.guard.proxy import run_proxy
from agentbox.manifest import AgentManifest
from agentbox.recorder import SessionRecorder


@dataclass
class GuardResult:
    exit_code: int
    violations: list = field(default_factory=list)
    summary: dict = field(default_factory=dict)
    session_id: str = ""
    blocked: bool = False
    block_reason: Optional[str] = None


def run_under_guard(manifest: AgentManifest, command: list,
                    *, base_dir: str = ".",
                    kill_on_block: bool = True,
                    extra_env: Optional[dict] = None) -> GuardResult:
    """
    Synchronous wrapper. Runs the proxy + subprocess until subprocess exits or
    a hard-block violation forces termination.
    """
    return asyncio.run(_run(manifest, command, base_dir, kill_on_block, extra_env or {}))


async def _run(manifest: AgentManifest, command: list,
               base_dir: str, kill_on_block: bool, extra_env: dict) -> GuardResult:
    recorder = SessionRecorder(
        agent_name=manifest.name,
        agent_version=manifest.version,
        model=manifest.effective_model,
        base_dir=base_dir,
    )
    policy = PolicyEngine(manifest)

    # Mutable state for the on_block callback
    block_state = {"violation": None, "kill": False}
    proc_holder = {"proc": None}

    def _on_block(violation: PolicyViolation):
        if block_state["violation"] is None:
            block_state["violation"] = violation
        if kill_on_block and proc_holder["proc"]:
            try:
                proc_holder["proc"].terminate()
            except ProcessLookupError:
                pass

    async with run_proxy(manifest, recorder, policy, on_block=_on_block) as base_url:
        env = os.environ.copy()
        env.update(extra_env)
        # Point provider SDKs at the proxy
        env["ANTHROPIC_BASE_URL"] = f"{base_url}/anthropic"
        env["OPENAI_BASE_URL"] = f"{base_url}/openai/v1"
        env["AGENTBOX_GUARD_ACTIVE"] = "1"
        env["AGENTBOX_SESSION_ID"] = recorder.session.session_id

        # Print a banner so users know guard is active
        print(
            f"[agentbox guard] Proxy listening on {base_url}\n"
            f"[agentbox guard] Wrapping: {' '.join(command)}\n"
            f"[agentbox guard] Session: {recorder.session.session_id}\n"
            f"[agentbox guard] Active guardrails: {_describe_active(policy)}\n",
            file=sys.stderr,
        )

        # Spawn the agent
        try:
            proc = await asyncio.create_subprocess_exec(
                *command,
                env=env,
                stdout=None,  # inherit so user sees agent output live
                stderr=None,
            )
            proc_holder["proc"] = proc
            exit_code = await proc.wait()
        except FileNotFoundError as e:
            recorder.record_error(error=str(e), context="subprocess spawn")
            recorder.complete(status="error", error=str(e))
            return GuardResult(exit_code=127, violations=[], summary={}, session_id=recorder.session.session_id)

    # Finalize the session log
    final_status = "completed"
    if block_state["violation"] is not None:
        final_status = "guardrail_stopped"

    recorder.complete(status=final_status,
                       error=block_state["violation"].detail if block_state["violation"] else None)

    summary = policy.summary()
    violation = block_state["violation"]
    return GuardResult(
        exit_code=exit_code if not block_state["violation"] else 137,
        violations=[violation] if violation else [],
        summary=summary,
        session_id=recorder.session.session_id,
        blocked=violation is not None,
        block_reason=violation.detail if violation else None,
    )


def _describe_active(policy: PolicyEngine) -> str:
    spec = policy.spec
    parts = []
    if spec.cost.max_usd_per_session is not None:
        parts.append(f"cost<=${spec.cost.max_usd_per_session}")
    if spec.iterations.max_llm_calls is not None:
        parts.append(f"llm_calls<={spec.iterations.max_llm_calls}")
    if spec.tools.allowlist:
        parts.append(f"tools={len(spec.tools.allowlist)} allowed")
    if spec.pii.patterns or spec.pii.action != "redact":
        parts.append(f"pii={spec.pii.action}")
    if spec.rate.max_calls_per_minute:
        parts.append(f"rate<={spec.rate.max_calls_per_minute}/min")
    return ", ".join(parts) or "<none — guardrails not configured>"
