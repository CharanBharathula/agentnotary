"""
AgentBox Session Recorder
=========================
Records every agent action for replay, debugging, and audit.
Like a flight recorder for AI agents.
"""

import json
import time
import uuid
import hashlib
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional


SESSIONS_DIR = ".agentbox/sessions"


@dataclass
class ActionRecord:
    """A single recorded action in an agent session."""
    timestamp: str
    action_type: str  # llm_call, tool_call, tool_result, decision, error, guardrail_triggered
    content: dict
    duration_ms: Optional[int] = None
    cost_usd: Optional[float] = None
    token_count: Optional[int] = None


@dataclass
class SessionRecord:
    """A complete recorded agent session."""
    session_id: str
    agent_name: str
    agent_version: str
    model: str
    started_at: str
    ended_at: Optional[str] = None
    status: str = "running"  # running, completed, failed, guardrail_stopped
    total_cost_usd: float = 0.0
    total_tokens: int = 0
    total_tool_calls: int = 0
    total_llm_calls: int = 0
    actions: list = field(default_factory=list)
    input_hash: str = ""  # hash of the original input for reproducibility
    error: Optional[str] = None

    def add_action(self, action: ActionRecord):
        self.actions.append(action)
        if action.cost_usd:
            self.total_cost_usd += action.cost_usd
        if action.token_count:
            self.total_tokens += action.token_count
        if action.action_type == "tool_call":
            self.total_tool_calls += 1
        if action.action_type == "llm_call":
            self.total_llm_calls += 1

    def complete(self, status: str = "completed", error: str = None):
        self.ended_at = datetime.utcnow().isoformat() + "Z"
        self.status = status
        self.error = error

    def duration_seconds(self) -> float:
        if not self.ended_at:
            return 0
        start = datetime.fromisoformat(self.started_at.replace("Z", "+00:00"))
        end = datetime.fromisoformat(self.ended_at.replace("Z", "+00:00"))
        return (end - start).total_seconds()

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "agent_name": self.agent_name,
            "agent_version": self.agent_version,
            "model": self.model,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "status": self.status,
            "total_cost_usd": round(self.total_cost_usd, 6),
            "total_tokens": self.total_tokens,
            "total_tool_calls": self.total_tool_calls,
            "total_llm_calls": self.total_llm_calls,
            "duration_seconds": round(self.duration_seconds(), 2),
            "input_hash": self.input_hash,
            "error": self.error,
            "actions": [asdict(a) for a in self.actions],
        }


class SessionRecorder:
    """Records agent sessions to disk."""

    def __init__(self, agent_name: str, agent_version: str, model: str, base_dir: str = "."):
        self.base_dir = Path(base_dir)
        self.sessions_dir = self.base_dir / SESSIONS_DIR
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

        self.session = SessionRecord(
            session_id=str(uuid.uuid4())[:12],
            agent_name=agent_name,
            agent_version=agent_version,
            model=model,
            started_at=datetime.utcnow().isoformat() + "Z",
        )

    def set_input_hash(self, input_text: str):
        self.session.input_hash = hashlib.sha256(input_text.encode()).hexdigest()[:16]

    def record_llm_call(self, prompt: str, response: str, duration_ms: int = 0,
                        cost_usd: float = 0, tokens: int = 0):
        self.session.add_action(ActionRecord(
            timestamp=datetime.utcnow().isoformat() + "Z",
            action_type="llm_call",
            content={"prompt_preview": prompt[:200], "response_preview": response[:200]},
            duration_ms=duration_ms,
            cost_usd=cost_usd,
            token_count=tokens,
        ))

    def record_tool_call(self, tool_name: str, args: dict, result: str,
                         duration_ms: int = 0, cost_usd: float = 0):
        self.session.add_action(ActionRecord(
            timestamp=datetime.utcnow().isoformat() + "Z",
            action_type="tool_call",
            content={"tool": tool_name, "args": args, "result_preview": str(result)[:200]},
            duration_ms=duration_ms,
            cost_usd=cost_usd,
        ))

    def record_decision(self, decision: str, reasoning: str = ""):
        self.session.add_action(ActionRecord(
            timestamp=datetime.utcnow().isoformat() + "Z",
            action_type="decision",
            content={"decision": decision, "reasoning": reasoning},
        ))

    def record_guardrail(self, guardrail_name: str, triggered_by: str, action_taken: str):
        self.session.add_action(ActionRecord(
            timestamp=datetime.utcnow().isoformat() + "Z",
            action_type="guardrail_triggered",
            content={
                "guardrail": guardrail_name,
                "triggered_by": triggered_by,
                "action_taken": action_taken,
            },
        ))

    def record_error(self, error: str, context: str = ""):
        self.session.add_action(ActionRecord(
            timestamp=datetime.utcnow().isoformat() + "Z",
            action_type="error",
            content={"error": error, "context": context},
        ))

    def complete(self, status: str = "completed", error: str = None):
        self.session.complete(status, error)
        self._save()
        return self.session

    def _save(self):
        filepath = self.sessions_dir / f"{self.session.session_id}.json"
        with open(filepath, "w") as f:
            json.dump(self.session.to_dict(), f, indent=2)


def list_sessions(base_dir: str = ".") -> list:
    """List all recorded sessions."""
    sessions_dir = Path(base_dir) / SESSIONS_DIR
    if not sessions_dir.exists():
        return []

    sessions = []
    for f in sorted(sessions_dir.glob("*.json"), reverse=True):
        try:
            with open(f) as fp:
                data = json.load(fp)
                sessions.append({
                    "session_id": data["session_id"],
                    "agent_name": data["agent_name"],
                    "version": data["agent_version"],
                    "status": data["status"],
                    "started_at": data["started_at"],
                    "cost": data["total_cost_usd"],
                    "tokens": data["total_tokens"],
                    "tools_called": data["total_tool_calls"],
                    "duration": data.get("duration_seconds", 0),
                })
        except (json.JSONDecodeError, KeyError):
            continue

    return sessions


def load_session(session_id: str, base_dir: str = ".") -> dict:
    """Load a specific session for replay."""
    sessions_dir = Path(base_dir) / SESSIONS_DIR
    filepath = sessions_dir / f"{session_id}.json"

    if not filepath.exists():
        # Try partial match
        matches = list(sessions_dir.glob(f"{session_id}*.json"))
        if matches:
            filepath = matches[0]
        else:
            raise FileNotFoundError(f"Session {session_id} not found")

    with open(filepath) as f:
        return json.load(f)
