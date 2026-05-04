"""
A toy "runaway" agent for the `agentnotary guard` demo.

Calls the Anthropic API in a tight loop with no termination condition.
Designed to demonstrate that AgentNotary's guard proxy will stop it
before it burns through the cost cap.

Run it WITHOUT a guard:
    python scripts/runaway_agent.py
        # If you actually have an API key, this could spend $$$ before you Ctrl-C.

Run it WITH a guard (the safe way):
    agentnotary guard run -- python scripts/runaway_agent.py
        # Guard's proxy intercepts every call and blocks at the manifest's
        # cost / iteration cap. Returns a provider-shaped 403 to the SDK.

Requires:
    pip install anthropic
    export ANTHROPIC_API_KEY=...      # or use guard's mock for E2E demos
"""

from __future__ import annotations

import os
import sys
import time

ITER_CAP = 100
PROMPT = "Repeat the word 'oops' once. Just one word."


def main() -> int:
    try:
        import anthropic  # type: ignore[import-not-found]
    except ImportError:
        sys.stderr.write(
            "[runaway-agent] anthropic SDK not installed.\n"
            "                pip install anthropic\n"
        )
        return 1

    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.stderr.write(
            "[runaway-agent] ANTHROPIC_API_KEY not set.\n"
            "                The agent would call the real API in a loop.\n"
        )
        return 1

    client = anthropic.Anthropic()
    print(f"[runaway-agent] starting infinite loop (cap: {ITER_CAP} iterations)...")

    for i in range(1, ITER_CAP + 1):
        print(f"[runaway-agent] call {i:03d}", flush=True)
        try:
            resp = client.messages.create(
                model="claude-sonnet-4-5-20251022",
                max_tokens=64,
                messages=[{"role": "user", "content": PROMPT}],
            )
            text = ""
            for block in resp.content:
                if hasattr(block, "text"):
                    text += block.text
            print(f"               → {text.strip()[:40]!r}")
        except Exception as e:
            # Guard's 403 lands here — the SDK raises its native exception.
            print(f"[runaway-agent] BLOCKED at call {i}: {type(e).__name__}: {e}")
            return 137
        time.sleep(0.05)

    print(f"[runaway-agent] hit ITER_CAP without being blocked — manifest cap missing?")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
