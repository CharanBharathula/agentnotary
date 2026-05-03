# AgentBox

**Docker for AI Agents.** Package, test, version, and govern your AI agents — across every framework.

```
pip install agentbox
agentbox init my-support-agent
agentbox test
agentbox tag v1.0.0
```

---

## Why AgentBox?

97% of companies have deployed AI agents. 82% can't track what agents they're running.

Software earned its infrastructure: Dockerfiles, CI/CD, semantic versioning, crash logs, rollbacks. AI agents have none of it. AgentBox brings the same discipline to agents:

| Problem | AgentBox Solution |
|---|---|
| "What agent are we running in prod?" | `agentbox.yaml` manifest — one file per agent |
| "Did the new prompt regress behavior?" | `agentbox test` — LLM-as-judge eval suite |
| "We need to rollback to last week's prompt" | `agentbox rollback v1.2.1` |
| "Why did the agent make that decision?" | `agentbox replay <session-id>` |
| "How many shadow agents exist in this repo?" | `agentbox scan ./src` |

---

## Install

```bash
pip install agentbox

# With LLM provider support (for running evals)
pip install "agentbox[anthropic]"
pip install "agentbox[openai]"
pip install "agentbox[all]"
```

**Requirements:** Python 3.9+

---

## Quick Start

### 1. Initialize an agent project

```bash
mkdir my-agent && cd my-agent
agentbox init my-support-agent
```

This creates:
```
my-agent/
├── agentbox.yaml          # Agent manifest (like a Dockerfile)
├── prompts/               # System prompts
├── evals/
│   └── test_suite.yaml    # Eval cases
└── .agentbox/             # State directory (.gitignore sessions/)
    ├── sessions/
    └── versions/
```

### 2. Edit your manifest

`agentbox.yaml` is the single source of truth for your agent:

```yaml
agent:
  name: my-support-agent
  version: 0.1.0
  description: Customer support agent
  model: claude-sonnet-4-20250514
  framework: anthropic

  tools:
    - name: search_kb
      type: function
    - name: create_ticket
      type: api
      endpoint: https://api.helpdesk.internal/tickets

  guardrails:
    - no-pii: "SSN|credit card|password"
    - cost-cap: "0.10"

  memory: conversation
  eval_suite: ./evals/test_suite.yaml
```

### 3. Write evals

```yaml
# evals/test_suite.yaml
suite: my-support-agent-evals
version: "1"

cases:
  - name: basic-greeting
    input: "Hello, I need help"
    expected_behavior: "Greets the user warmly and asks how it can help"
    max_latency_ms: 3000
    max_cost_usd: 0.02

  - name: escalate-angry-customer
    input: "This is unacceptable! I've been waiting 3 weeks!"
    expected_behavior: "Acknowledges frustration, apologizes, offers immediate escalation"
    must_call_tools: [create_ticket]
```

### 4. Validate, test, and version

```bash
agentbox validate          # Check manifest for issues
agentbox test              # Run eval suite (uses LLM as judge)
agentbox test --verbose    # Show full LLM responses
agentbox tag v0.1.0        # Snapshot current state
```

---

## All Commands

```
agentbox init [name]           Initialize a new agent project
agentbox validate              Validate the current agent manifest
agentbox test [--verbose]      Run eval suite against the agent
agentbox tag <version>         Tag current state as a version
agentbox versions              List all tagged versions
agentbox rollback <version>    Rollback to a tagged version
agentbox sessions              List recorded sessions
agentbox replay <session-id>   Replay a recorded session (flight recorder)
agentbox scan [directory]      Discover agents across a codebase
agentbox info                  Show current agent info
```

---

## Session Recording

Wire the flight recorder into your agent to capture every LLM call, tool invocation, and decision:

```python
from agentbox.recorder import SessionRecorder

recorder = SessionRecorder(agent_name="my-support-agent", version="0.1.0")

# In your agent loop
recorder.record_llm_call(
    prompt=user_message,
    response=llm_response,
    duration_ms=450,
    cost_usd=0.003,
    tokens={"input": 120, "output": 80},
)
recorder.record_tool_call("search_kb", {"query": "refund policy"}, result)
recorder.record_decision("escalate", reasoning="user expressed anger 3 times")
recorder.complete(status="completed")
```

Then replay any session:

```bash
agentbox sessions
agentbox replay abc123
```

```
⬡ AgentBox — Replaying session: abc123

  → Agent: my-support-agent v0.1.0
  → Cost: $0.0042

  [1] 🤖 llm_call (312ms) ($0.0018)
      prompt: Hello, I need help with my order
      response: Hi! I'd be happy to help. Could you share your order number?
  [2] 🔧 tool_call
      tool: search_kb
      args: {"query": "order lookup"}
  [3] 💡 decision
      decision: escalate
      reasoning: user expressed anger 3 times
```

---

## Shadow Agent Scanner

Find every AI agent lurking in a codebase — before someone else does:

```bash
agentbox scan ./backend
```

```
  → Files scanned: 847
  → Agents found: 12

  FILE                          LINE  FRAMEWORK   MODEL           TOOLS  GUARDRAILS
  ─────────────────────────────────────────────────────────────────────────────────
  services/support/agent.py      23   anthropic   claude-sonnet   ✓      ✗
  scripts/bulk_email.py          11   openai_sdk  gpt-4o          ✗      ✗
  workflows/data_pipeline.py     44   langchain   unknown         ✓      ✗
  ...

  ⚠  9 ungoverned agents found (no guardrails detected)
```

Detects: LangChain, CrewAI, AutoGen, OpenAI SDK, Anthropic SDK, LlamaIndex, DSPy.

---

## Version Control & Rollback

```bash
# Ship a new prompt
agentbox tag v1.1.0

# Something broke in prod?
agentbox rollback v1.0.3
# Current state is auto-saved as pre-rollback-{timestamp} before restoring
```

---

## Manifest Reference

```yaml
name: string                     # Required. Agent name
version: string                  # Required. Semantic version
description: string              # Optional. Human-readable description
model: string                    # Required. Model ID
framework: string                # Required. langchain|crewai|autogen|openai|anthropic|custom
system_prompt: string            # Optional. Inline or file:// path
entry_point: string              # Optional. Python module:function

tools:
  - name: string                 # Tool identifier
    type: builtin|mcp|api|function
    endpoint: string             # For type: api or mcp
    auth: ENV_VAR_NAME           # Env var holding the auth token

guardrails:
  - name: string
    rule: must_not_contain|max_cost_usd|max_latency_ms|...
    value: string

memory: none|conversation|summary|vector
eval_suite: ./evals/test_suite.yaml
```

---

## Roadmap

- [ ] **AgentBox Registry** — Push/pull agent manifests like Docker images (`agentbox push`, `agentbox pull`)
- [ ] **Cloud Dashboard** — Web UI for teams: session explorer, eval trends, cost tracking
- [ ] **`agentbox deploy`** — One-command deployment to major agent hosting platforms
- [ ] **Live cost alerting** — Slack/email alerts when session cost exceeds threshold
- [ ] **SBOM for agents** — Software Bill of Materials: every model, tool, and prompt in one audit trail
- [ ] **MCP manifest support** — First-class Model Context Protocol tool declarations
- [ ] **GitHub Action** — `agentbox test` in CI, fail PRs that break evals

---

## Contributing

AgentBox is Apache 2.0 licensed and actively looking for contributors.

```bash
git clone https://github.com/CharanBharathula/agentbox
cd agentbox
pip install -e ".[dev]"
pytest
```

Areas where help is needed:
- Framework detection patterns (LlamaIndex, DSPy, Haystack, Semantic Kernel)
- Eval runner integrations (run against real agent endpoints)
- Registry design (manifest format spec)

Open an issue or PR on GitHub.

---

## License

Apache 2.0 — see [LICENSE](LICENSE).

Built by [CharanBharathula](https://github.com/CharanBharathula). Inspired by Docker, but for the AI agent era.
