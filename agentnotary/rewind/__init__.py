"""
agentnotary.rewind
===============
Time-travel debugging for AI agents.

Reads a recorded session, lets the user fork at any step, optionally edit the
prompt at that step, and re-runs forward — re-using recorded LLM responses
for unchanged turns and only spending real tokens for the diverged path.

Public API:
    rewind_session(session_id, base_dir, fork_step=None, edit_prompt=None) -> RewindResult
    diff_step(session_id, base_dir, step) -> dict
"""

from agentnotary.rewind.runner import (
    RewindResult,
    RewindStep,
    diff_step,
    list_steps,
    rewind_session,
)

__all__ = [
    "RewindResult",
    "RewindStep",
    "diff_step",
    "list_steps",
    "rewind_session",
]
