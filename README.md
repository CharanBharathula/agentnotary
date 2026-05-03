# AgentBox

**The declarative governance spec for AI agents.** Open-source. Apache 2.0.
Three commands: **declare → seal → enforce → document.**

```bash
pip install agentbox
agentbox init my-agent
agentbox seal                                       # Cargo.lock for AI agents
agentbox guard run -- python my_agent.py            # Block runaway loops at the API boundary
agentbox compliance --standard eu-ai-act            # Auto-generate Annex IV docs
```

[![CI](https://github.com/CharanBharathula/agentbox/actions/workflows/ci.yml/badge.svg)](https://github.com/CharanBharathula/agentbox/actions)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)

---

## Why

97% of companies have deployed AI agents. 82% can't track what agents they're running. Every existing observability tool — LangSmith, Langfuse, Helicone, AgentOps — only **watches** what happened. None of them:

- **Prevent** runaway loops at the API boundary (passive observation, not enforcement)
- **Prove** an agent hasn't drifted (no cryptographic seal)
- **Document** the agent for regulators (EU AI Act enforcement begins August 2, 2026)

AgentBox owns that empty position. It sits **alongside** your observability stack, not against it.

| Problem | AgentBox solution |
|---|---|
| "Did our prompt change behavior?" | `agentbox seal --verify` — fails if anything drifted |
| "Why did the agent burn $4,000 overnight?" | `agentbox guard` — would have blocked it at $1.00 |
| "We need EU AI Act docs by August" | `agentbox compliance --standard eu-ai-act` |
| "Provider silently updated the model" | Probe-response hash in `agent.lock` catches it |
| "What agents exist in our codebase?" | `agentbox scan ./src` finds them across 7 frameworks |

---

## Install

```bash
pip install agentbox

# Optional extras
pip install "agentbox[anthropic]"   # for live LLM evals
pip install "agentbox[openai]"
pip install "agentbox[pii]"         # Presidio NER for stronger PII detection
pip install "agentbox[all]"
```

**Requirements:** Python 3.9+

---

## The three commands

### 1. `agentbox seal` — Cargo.lock for AI agents

Produces `agent.lock` — a cryptographically-hashed snapshot of *everything* that defines your agent. Manifest, prompts (raw + normalized), tool source code, MCP package versions, dependency lockfile, environment expectations.

Commit `agent.lock` next to `agentbox.yaml`. Now you can:

```bash
agentbox seal             # write agent.lock
agentbox seal --verify    # fail CI if anything has drifted
agentbox seal --probe     # also hash a canonical-prompt response
agentbox seal diff other.lock
```

The optional `--probe` flag sends a fixed prompt at temperature 0 and hashes the model's response. If your provider silently swaps weights behind the same model name, the next seal's probe hash diverges. **No other agent tool does this.**

### 2. `agentbox guard run -- <command>` — runtime enforcement

A local HTTP reverse proxy that wraps your agent's LLM provider calls. Framework-agnostic — works with anything that respects `ANTHROPIC_BASE_URL` / `OPENAI_BASE_URL`.

```bash
agentbox guard run -- python -m my_agent
```

Enforces typed guardrails declared in `agentbox.yaml`:

- **`cost`** — per-call and per-session USD caps
- **`iterations`** — max LLM calls, max tool calls
- **`tools`** — allowlist / denylist / require_approval
- **`pii`** — redact or block SSN, email, credit-card patterns at the wire
- **`content`** — max input tokens, blocked phrases
- **`rate`** — per-minute and per-session

Blocked calls return a **provider-shaped 403** so your SDK raises its native exception class. Every existing observability tool is passive — guard is the only one that intercepts.

### 3. `agentbox compliance --standard eu-ai-act` — regulator-ready docs

Combines manifest + seal + recent sessions + a deterministic risk classifier into EU AI Act Annex IV technical documentation. Markdown for engineers (committable, diffable in PRs), JSON for GRC tools (OneTrust, ServiceNow GRC, Drata, Vanta).

```bash
agentbox compliance --check                                  # CI mode: fails if metadata is missing
agentbox compliance --standard eu-ai-act --output ./docs     # writes .md + .json
```

The risk classifier is a **rule engine, not an LLM call.** Every classification cites the rule that fired (`EU-AI-ACT-ANNEX-III-payment` triggered by keyword `payment` in tools/description), so a compliance officer can audit the classifier itself.

> ⚠️ **Important:** Generated documentation is a *scaffold only — not legal advice.* Review by qualified counsel and a notified body is required before regulatory submission.

---

## Quickstart

```bash
mkdir my-agent && cd my-agent
agentbox init refund-bot
```

Edit `agentbox.yaml`:

```yaml
apiVersion: agentbox/v0.2
agent:
  name: refund-bot
  version: 0.1.0

  framework: anthropic
  model:
    provider: anthropic
    name: claude-sonnet-4-5-20251022
    pinned_version: claude-sonnet-4-5-20251022
    temperature: 0.2
    max_tokens: 2048

  system_prompt_file: ./prompts/system.md

  tools:
    - { name: lookup_order, type: function, module: app.tools:lookup_order }
    - { name: process_refund, type: api,
        endpoint: https://api.acme.com/refunds, auth: ACME_KEY }

  guardrails:
    cost:       { max_usd_per_session: 0.50, max_usd_per_call: 0.10, action: block }
    iterations: { max_llm_calls: 25, action: block }
    tools:      { allowlist: [lookup_order, process_refund],
                  require_approval: [process_refund] }
    pii:        { patterns: [SSN, EMAIL, CREDIT_CARD], action: redact, direction: both }
    rate:       { max_calls_per_minute: 60 }

  entry_point:
    command: "python -m refund_bot"
    env_vars: [ANTHROPIC_API_KEY, ACME_KEY]

  compliance:
    risk_class: limited
    affected_users: external_consumers
    human_oversight: review_required
    intended_purpose: |
      Resolves Tier-1 customer refund requests for orders under $50.
    out_of_scope: [chargebacks, subscriptions]
    data_handling:
      processes_pii: true
      pii_categories: [name, email, order_id]
      retention_days: 90
```

Then ship the governance loop:

```bash
agentbox seal                                     # lock the agent
agentbox guard run -- python -m refund_bot        # run with enforcement
agentbox compliance --standard eu-ai-act --output ./docs
git add agentbox.yaml agent.lock docs/ && git commit
```

---

## All commands

```text
Govern (v0.2):
  seal [--probe]          Lock the agent into a reproducible snapshot
  seal --verify           Verify nothing has drifted since the last seal
  guard run -- <cmd>      Run an agent under runtime enforcement
  compliance              Generate regulatory documentation (EU AI Act, ...)

Develop:
  init [name]             Create a new agent project
  validate                Validate agent manifest
  test [--verbose]        Run eval suite
  info                    Show current agent details

Versioning:
  tag <version>           Tag current state (e.g., v1.0.0)
  versions                List all tagged versions
  rollback <version>      Restore a tagged version

Observe:
  sessions                List recorded sessions
  replay <session-id>     Replay a recorded session
  scan [directory]        Discover agents in codebase
```

---

## How it compares

| | AgentBox | LangSmith | Langfuse | Helicone | AgentOps |
|---|---|---|---|---|---|
| Tracing & evals | ✅ basic | ✅ deep | ✅ deep | ✅ basic | ✅ deep |
| Cost tracking | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Active enforcement** | ✅ proxy blocks | ❌ passive | ❌ passive | ❌ passive | ❌ passive |
| **Cryptographic seal** | ✅ `agent.lock` | ❌ | ❌ | ❌ | ❌ |
| **Provider-drift probe** | ✅ probe hash | ❌ | ❌ | ❌ | ❌ |
| **EU AI Act docs** | ✅ Annex IV gen | ❌ | ❌ | ❌ | ❌ |
| Open source | ✅ Apache 2.0 | ❌ | ✅ | ✅ partial | ✅ partial |
| Framework lock-in | ❌ none | LangChain-first | none | none | none |

**Position:** AgentBox is the declarative spec / governance layer. Existing observability tools are dashboards. They're complementary, not competing.

---

## Roadmap

**v0.2.0 (this release)** — seal, guard, compliance. EU AI Act Annex IV.
**v0.2.1** — streaming proxy support. Pricing-table refresh GitHub Action. Wider PII regex coverage.
**v0.2.x** — NIST AI RMF and ISO/IEC 42001 compliance templates.
**v0.3** — `simulate` (cost dry-run with synthetic input distribution); `drift` (daily baseline comparison); AST-based scanner.
**v0.4** — `build --target {openai-agents-sdk, crewai}` compiler; AgentBox Hub registry.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) and [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

```bash
git clone https://github.com/CharanBharathula/agentbox
cd agentbox
pip install -e ".[dev]"
pytest tests/ -q          # 121 tests, ~3 seconds
ruff check agentbox/ tests/
```

We're especially looking for help with:
- Additional compliance templates (NIST AI RMF, ISO/IEC 42001)
- PII detection improvements (international formats, obfuscation evasion)
- Streaming proxy support
- Risk classifier rules for non-US jurisdictions

---

## License

[Apache 2.0](LICENSE) — use it commercially, fork it, embed it. Just keep the notice.

Built by [@CharanBharathula](https://github.com/CharanBharathula).
The `agent.lock` format is a public spec; we want it on every agent in production.
