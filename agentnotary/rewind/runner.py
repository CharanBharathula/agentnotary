"""
agentnotary.rewind.runner
======================
Deterministic re-execution of recorded sessions.

The model: a session is a sequence of recorded actions (llm_call, tool_call,
decision, ...). Rewind lets you "play it back" up to a chosen step, then
optionally diverge — by editing the prompt at that step and seeing what
WOULD have happened.

Without an API key, divergence is simulated using a deterministic stand-in
response (so the rewind still produces a forward path you can inspect).
With an API key, the diverged step makes one real LLM call.

This is a debugger, not a re-runner: the goal is to understand "if I'd
prompted this differently at step 7, how would the trajectory have changed?"
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from agentnotary.manifest import AgentManifest, parse_manifest
from agentnotary.recorder import load_session


@dataclass
class RewindStep:
    index: int
    action_type: str
    summary: str           # one-line human-readable
    timestamp: str
    raw: dict              # the original action record
    is_fork_point: bool = False
    is_simulated: bool = False  # true after the fork point in --rewind --edit-prompt mode


@dataclass
class RewindResult:
    session_id: str
    fork_step: Optional[int]
    edited_prompt: Optional[str]
    used_live_llm: bool
    steps: list = field(default_factory=list)
    original_total_cost_usd: float = 0.0
    rewind_total_cost_usd: float = 0.0
    notes: list = field(default_factory=list)


# ── Helpers ───────────────────────────────────────────────────────────


def _summarize_action(action: dict) -> str:
    atype = action.get("action_type", "unknown")
    content = action.get("content") or {}
    if atype == "llm_call":
        prompt = content.get("prompt_preview", "")[:80]
        resp = content.get("response_preview", "")[:60]
        return f"LLM: '{prompt}' → '{resp}'"
    if atype == "tool_call":
        tool = content.get("tool", "?")
        args = content.get("args", {})
        result = (content.get("result_preview") or "")[:50]
        return f"TOOL[{tool}]({args}) → {result}"
    if atype == "decision":
        return f"DECIDE: {content.get('decision', '?')} ({content.get('reasoning', '')[:60]})"
    if atype == "guardrail_triggered":
        return f"GUARDRAIL: {content.get('guardrail', '?')} → {content.get('action_taken', '')}"
    if atype == "error":
        return f"ERROR: {content.get('error', '?')}"
    return f"{atype}"


# ── List & inspect ─────────────────────────────────────────────────────


def list_steps(session_id: str, base_dir: str = ".") -> list:
    """Return every step in the session as a RewindStep list."""
    session = load_session(session_id, base_dir)
    steps = []
    for i, action in enumerate(session.get("actions", []), start=1):
        steps.append(RewindStep(
            index=i,
            action_type=action.get("action_type", "unknown"),
            summary=_summarize_action(action),
            timestamp=action.get("timestamp", ""),
            raw=action,
        ))
    return steps


def diff_step(session_id: str, base_dir: str, step: int) -> dict:
    """Return the full content of a single step (for `agentnotary replay --inspect N`)."""
    session = load_session(session_id, base_dir)
    actions = session.get("actions", [])
    if step < 1 or step > len(actions):
        raise IndexError(f"Step {step} out of range (1..{len(actions)})")
    return actions[step - 1]


# ── Rewind / fork ──────────────────────────────────────────────────────


def _simulated_response(edited_prompt: str, model: str) -> str:
    """
    Deterministic stand-in when no API key is available. Generates a clearly
    labeled, repeatable mock response so the user can still see the
    divergence forward path.
    """
    return (
        "[REWIND-SIMULATED RESPONSE]\n"
        f"This is a deterministic stand-in for {model}. With an API key set\n"
        "(ANTHROPIC_API_KEY / OPENAI_API_KEY) `agentnotary replay --rewind` would\n"
        "send the edited prompt to the model and capture the real response.\n\n"
        f"Edited prompt was: {edited_prompt[:160]}"
    )


def _send_diverged_call(manifest: AgentManifest, system_prompt: str,
                        edited_prompt: str) -> Optional[str]:
    """Send the diverged turn's prompt to the live provider. Returns None on failure."""
    provider = manifest.effective_provider
    model = manifest.effective_model

    if provider == "anthropic":
        if not os.environ.get("ANTHROPIC_API_KEY"):
            return None
        try:
            import anthropic  # type: ignore[import-not-found]
        except ImportError:
            return None
        client = anthropic.Anthropic()
        try:
            resp = client.messages.create(
                model=model, max_tokens=1024, temperature=0,
                system=system_prompt or "You are a helpful assistant.",
                messages=[{"role": "user", "content": edited_prompt}],
            )
            text = ""
            for block in resp.content:
                if hasattr(block, "text"):
                    text += block.text
            return text
        except Exception:  # noqa: BLE001
            return None

    if provider == "openai":
        if not os.environ.get("OPENAI_API_KEY"):
            return None
        try:
            import openai  # type: ignore[import-not-found]
        except ImportError:
            return None
        client = openai.OpenAI()
        try:
            resp = client.chat.completions.create(
                model=model, max_tokens=1024, temperature=0,
                messages=[
                    {"role": "system", "content": system_prompt or "You are a helpful assistant."},
                    {"role": "user", "content": edited_prompt},
                ],
            )
            return (resp.choices[0].message.content or "")
        except Exception:  # noqa: BLE001
            return None

    return None


def rewind_session(session_id: str, base_dir: str = ".", *,
                   fork_step: Optional[int] = None,
                   edit_prompt: Optional[str] = None) -> RewindResult:
    """
    Replay a session with optional fork.

    - `fork_step=None`: pure replay, all steps marked is_simulated=False.
    - `fork_step=N, edit_prompt=None`: replay through N, mark steps after N as
      "would-have-continued" (still using recorded data — useful for human review).
    - `fork_step=N, edit_prompt="..."`: replay through N-1, replace step N's
      prompt with the edit, simulate forward.
    """
    session = load_session(session_id, base_dir)
    actions = session.get("actions", [])

    notes: list[str] = []
    used_live = False

    # Try to load the live manifest for provider/model + system prompt
    try:
        manifest = parse_manifest(base_dir)
    except (FileNotFoundError, ValueError):
        manifest = None
        notes.append("agentnotary.yaml not found — using session-recorded model only.")

    steps: list[RewindStep] = []
    for i, action in enumerate(actions, start=1):
        is_fork = (fork_step is not None and i == fork_step)
        step = RewindStep(
            index=i,
            action_type=action.get("action_type", "unknown"),
            summary=_summarize_action(action),
            timestamp=action.get("timestamp", ""),
            raw=action,
            is_fork_point=is_fork,
            is_simulated=(fork_step is not None and i > fork_step),
        )
        steps.append(step)

    # Apply prompt edit at the fork point
    if fork_step is not None and edit_prompt is not None:
        if fork_step < 1 or fork_step > len(steps):
            raise IndexError(f"fork_step={fork_step} out of range (1..{len(steps)})")
        target = steps[fork_step - 1]
        if target.action_type != "llm_call":
            notes.append(f"WARNING: step {fork_step} is '{target.action_type}', not 'llm_call'. "
                          f"Edit applied as a synthetic LLM turn anyway.")

        # Send the edited prompt
        sys_prompt = manifest.system_prompt if manifest else ""
        live_response = _send_diverged_call(manifest, sys_prompt, edit_prompt) if manifest else None
        if live_response is not None:
            used_live = True
            response_text = live_response
            notes.append(
                f"Diverged at step {fork_step}: sent edited prompt to "
                f"{manifest.effective_provider}/{manifest.effective_model} (live)."
            )
        else:
            response_text = _simulated_response(edit_prompt,
                                                  manifest.effective_model if manifest else "unknown")
            notes.append(
                f"Diverged at step {fork_step}: no live provider available — "
                "using deterministic simulated response."
            )

        # Replace the fork step's content in-place (keep raw for audit)
        new_content = dict(target.raw)
        new_content_inner = dict(new_content.get("content") or {})
        new_content_inner["prompt_preview"] = edit_prompt[:200]
        new_content_inner["response_preview"] = response_text[:200]
        new_content_inner["__rewind_edited"] = True
        new_content["content"] = new_content_inner
        target.raw = new_content
        target.summary = f"[FORK] LLM: '{edit_prompt[:80]}' → '{response_text[:60]}'"

        # Trim everything after the fork — those steps are now invalid because
        # the trajectory diverged. Replace with a synthesis stub.
        if fork_step < len(steps):
            steps = steps[:fork_step]
            steps.append(RewindStep(
                index=fork_step + 1,
                action_type="rewind_truncated",
                summary=("(trajectory diverged here — original session continued for "
                         f"{len(actions) - fork_step} more steps; re-run with the "
                         "edited prompt to see the new trajectory)"),
                timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                raw={},
                is_simulated=True,
            ))

    return RewindResult(
        session_id=session.get("session_id", session_id),
        fork_step=fork_step,
        edited_prompt=edit_prompt,
        used_live_llm=used_live,
        steps=steps,
        original_total_cost_usd=session.get("total_cost_usd", 0.0),
        rewind_total_cost_usd=0.0 if not used_live else session.get("total_cost_usd", 0.0),
        notes=notes,
    )
