# AgentNotary

**Notarize, govern, and audit AI agents.** Open-source. Apache 2.0.

```bash
pip install agentnotary
agentnotary init my-agent
agentnotary seal                                       # Cargo.lock for AI agents
agentnotary guard run -- python my_agent.py            # block runaway loops at the API boundary
agentnotary compliance --standard eu-ai-act            # auto-generate Annex IV docs
agentnotary attack --suite owasp-llm-top10             # adversarial fuzzer
agentnotary bom --format cyclonedx                     # AI Bill of Materials
agentnotary bench --models claude-sonnet-4,gpt-4o      # cost-vs-accuracy Pareto
agentnotary replay <session> --rewind --step 5         # time-travel debugger
```

[![CI](https://github.com/CharanBharathula/agentnotary/actions/workflows/ci.yml/badge.svg)](https://github.com/CharanBharathula/agentnotary/actions)
[![PyPI](https://img.shields.io/pypi/v/agentnotary.svg)](https://pypi.org/project/agentnotary/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)

---

## Why AgentNotary

97% of companies have deployed AI agents. 82% can't track what agents they're running. Every existing observability tool — LangSmith, Langfuse, Helicone, AgentOps — only **watches** what happened. None of them:

- **Prevent** runaway loops at the API boundary (passive observation, not enforcement)
- **Prove** an agent hasn't drifted (no cryptographic seal)
- **Document** the agent for regulators (EU AI Act enforcement begins August 2, 2026)
- **Probe** the agent for vulnerabilities (no built-in attack suite)
- **Catalog** the agent's components (no AI-BOM)

AgentNotary occupies that empty position. It sits **alongside** your observability stack, not against it. Think of it as the **notary public for AI agents** — it certifies, seals, witnesses, archives, and produces evidence.

| Problem | AgentNotary solution |
|---|---|
| "Did our prompt change behavior?" | `agentnotary seal --verify` — fails if anything drifted |
| "Why did the agent burn $4,000 overnight?" | `agentnotary guard` — would have blocked it at $1.00 |
| "We need EU AI Act docs by August" | `agentnotary compliance --standard eu-ai-act` |
| "Provider silently updated the model" | Probe-response hash in `agent.lock` catches it |
| "Procurement wants an AI-BOM" | `agentnotary bom --format cyclonedx` (also SPDX) |
| "Should we use Sonnet or 4o?" | `agentnotary bench` — Pareto chart in 90 seconds |
| "Is our agent vulnerable to prompt injection?" | `agentnotary attack --suite owasp-llm-top10` |
| "Why did the agent take that path at step 7?" | `agentnotary replay <id> --rewind --step 7 --edit '...'` |

---

## Install

```bash
pip install agentnotary

# Optional extras
pip install "agentnotary[anthropic]"   # for live LLM evals + attack runs
pip install "agentnotary[openai]"
pip install "agentnotary[pii]"         # Presidio NER for stronger PII detection
pip install "agentnotary[all]"
```

**Requirements:** Python 3.9+

---

## The eight commands

### Notarize & Govern (the core thesis)

#### `agentnotary seal` — Cargo.lock for AI agents

Cryptographically-hashed snapshot of *everything* that defines your agent. Manifest, prompts (raw + normalized), tool source code, MCP package versions, dependencies. Optional `--probe` flag detects silent provider weight updates.

```bash
agentnotary seal             # write agent.lock
agentnotary seal --verify    # fail CI if anything has drifted
agentnotary seal --probe     # also hash a canonical-prompt response
agentnotary seal diff other.lock
```

#### `agentnotary guard run` — runtime enforcement

Local HTTP reverse proxy. Framework-agnostic. Blocks at the API boundary based on typed guardrails declared in `agentnotary.yaml`:

- **`cost`** — per-call and per-session USD caps
- **`iterations`** — max LLM calls, max tool calls
- **`tools`** — allowlist / denylist / require_approval
- **`pii`** — redact or block SSN, email, credit-card patterns
- **`content`** — max input tokens, blocked phrases
- **`rate`** — per-minute and per-session

Blocked calls return a **provider-shaped 403** so your SDK raises its native exception class. Every existing observability tool is passive — guard is the only one that intercepts.

#### `agentnotary compliance --standard eu-ai-act`

EU AI Act Annex IV technical documentation, generated deterministically from manifest + seal + sessions. Markdown for engineers, JSON for GRC tools.

The risk classifier is a **rule engine, not an LLM call.** Every classification cites the rule that fired (`EU-AI-ACT-ANNEX-III-payment` triggered by keyword `payment` in tools/description), so a compliance officer can audit the classifier itself.

> ⚠️ **Important:** Generated documentation is a *scaffold only — not legal advice.* Review by qualified counsel and a notified body is required before regulatory submission.

### Audit & Test (v0.3)

#### `agentnotary bom` — AI Bill of Materials

CycloneDX 1.6 (OWASP) and SPDX 2.3 (Linux Foundation) compliant SBOMs. Enumerates models, prompts, tools, MCP servers, and dependencies — each with cryptographic hashes.

```bash
agentnotary bom --format cyclonedx   # → agent.sbom.cdx.json
agentnotary bom --format spdx        # → agent.sbom.spdx.json
```

#### `agentnotary bench` — Cross-model Pareto

Run the eval suite against multiple models in parallel. Output: ASCII Pareto chart of cost vs accuracy.

```bash
agentnotary bench --models claude-sonnet-4-5-20251022,gpt-4o,gpt-4o-mini,gemini-2.5-flash
```

Without API keys: dry-run mode projects cost from prompt size + the static pricing table. With keys: live measurement.

#### `agentnotary attack` — Adversarial fuzzer

Bundled OWASP LLM Top 10 attack corpus. Tests prompt injection, system-prompt leakage, credential extraction, excessive agency, and more. Reports a vulnerability rate and per-attack evidence.

```bash
agentnotary attack --suite owasp-llm-top10           # dry-run (predicts blockability)
agentnotary attack --suite owasp-llm-top10 --live    # sends real prompts
```

#### `agentnotary replay <session-id> --rewind` — Time-travel debugging

Replay any recorded session, fork at any step, edit the prompt, simulate forward.

```bash
agentnotary replay abc123                                              # basic replay
agentnotary replay abc123 --rewind --step 7 --edit "What if I asked..."  # fork + diverge
```

Without an API key: deterministic stand-in for the diverged turn (so you can still see the structure). With a key: real LLM call for the diverged step only.

### Develop / Versioning / Observability

```text
init [name]              Create a new agent project
validate                 Validate agent manifest
test [--verbose]         Run eval suite
info                     Show current agent details
tag <version>            Tag current state
versions / rollback      List or restore tagged versions
sessions                 List recorded sessions
scan [directory]         Discover agents across a codebase
```

---

## How it compares

| | AgentNotary | LangSmith | Langfuse | Helicone | AgentOps |
|---|---|---|---|---|---|
| Tracing & evals | ✅ basic | ✅ deep | ✅ deep | ✅ basic | ✅ deep |
| Cost tracking | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Active enforcement** | ✅ proxy blocks | ❌ passive | ❌ passive | ❌ passive | ❌ passive |
| **Cryptographic seal** | ✅ `agent.lock` | ❌ | ❌ | ❌ | ❌ |
| **Provider-drift probe** | ✅ probe hash | ❌ | ❌ | ❌ | ❌ |
| **EU AI Act docs** | ✅ Annex IV gen | ❌ | ❌ | ❌ | ❌ |
| **AI-BOM (CycloneDX/SPDX)** | ✅ | ❌ | ❌ | ❌ | ❌ |
| **Adversarial fuzzer** | ✅ OWASP suite | ❌ | ❌ | ❌ | ❌ |
| **Time-travel replay** | ✅ `--rewind` | ❌ | partial | ❌ | partial |
| **Cross-model bench** | ✅ Pareto | ❌ | ❌ | ❌ | ❌ |
| Open source | ✅ Apache 2.0 | ❌ | ✅ | ✅ partial | ✅ partial |
| Framework lock-in | ❌ none | LangChain-first | none | none | none |

**Position:** AgentNotary is the trust primitive. They watch agents. We *certify* agents.

---

## Quickstart

```bash
mkdir my-agent && cd my-agent
agentnotary init refund-bot
```

Edit `agentnotary.yaml`:

```yaml
apiVersion: agentnotary/v0.2
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
    tools:      { allowlist: [lookup_order, process_refund] }
    pii:        { patterns: [SSN, EMAIL, CREDIT_CARD], action: redact, direction: both }
    rate:       { max_calls_per_minute: 60 }

  entry_point:
    command: "python -m refund_bot"
    env_vars: [ANTHROPIC_API_KEY, ACME_KEY]

  compliance:
    risk_class: limited
    affected_users: external_consumers
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
agentnotary seal                                    # notarize
agentnotary attack                                  # adversarial check
agentnotary guard run -- python -m refund_bot       # enforce at runtime
agentnotary compliance --standard eu-ai-act         # certify
agentnotary bom --format cyclonedx                  # AI-BOM for procurement
git add agentnotary.yaml agent.lock docs/ && git commit
```

---

## Migrating from `agentbox`

`agentnotary` was previously released as `agentbox`. v0.3.0 of `agentnotary` is the successor; manifests parse identically.

To migrate:
1. `pip uninstall agentbox && pip install agentnotary`
2. Rename `agentbox.yaml` → `agentnotary.yaml` (or leave it; `agentnotary` reads both)
3. Update `apiVersion: agentbox/v0.2` → `apiVersion: agentnotary/v0.2` (legacy is still accepted)
4. Old `.agentbox/` state directories continue to be supported alongside the new `.agentnotary/` directory.

The legacy `agentbox` repo is archived: https://github.com/CharanBharathula/agentbox.

---

## Roadmap

**v0.3.0 (this release)** — bom, bench, attack, replay-rewind. The "wow" suite.
**v0.3.x** — streaming proxy support, NIST AI RMF / ISO 42001 templates.
**v0.4** — Sigstore-style cryptographic signing + transparency log for `agent.lock`. Behavioral fingerprinting (replace single-prompt probe with N-prompt panel).
**v0.5** — AgentNotary Hub (public registry of sealed agents). `notarize push` / `notarize pull`.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) and [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

```bash
git clone https://github.com/CharanBharathula/agentnotary
cd agentnotary
pip install -e ".[dev]"
pytest tests/ -q          # 169 tests, ~8 seconds
ruff check agentnotary/ tests/
```

We're especially looking for help with:
- Cryptographic signing (Sigstore Rekor integration)
- Streaming proxy support in `guard`
- Wider attack corpus (Garak, AdvBench, prompt-injection wikis)
- NIST AI RMF and ISO/IEC 42001 compliance templates
- International PII patterns

---

## License

[Apache 2.0](LICENSE) — use it commercially, fork it, embed it. Just keep the notice.

Built by [@CharanBharathula](https://github.com/CharanBharathula).
The `agent.lock` format is a public spec; we want it on every agent in production.
