# Launch Kit — AgentNotary v0.3.0

Three drafts ready to copy-paste. Tweak the personal voice as needed; the structure is tested.

---

## 1. Hacker News — Show HN post

**Title (one of these — pick by which line you'd click):**

- `Show HN: AgentNotary – cryptographic seal, runtime guard, and EU AI Act docs for AI agents`
- `Show HN: AgentNotary – Cargo.lock + adversarial fuzzer + AI-BOM for AI agents`
- `Show HN: AgentNotary – the notary public for AI agents (open source)`

**Body:**

```
Hi HN,

I built AgentNotary because every AI agent observability tool I tried watches
agents but doesn't *certify* them. That's a different problem — and it's the
problem regulators, security teams, and procurement keep asking about.

AgentNotary is one CLI with eight commands. The four that matter most:

* `agentnotary seal` — Cargo.lock for AI agents. Cryptographically hashes the
  manifest, prompts (raw + normalized), tool source, MCP package versions,
  and dependencies. Optional `--probe` flag detects silent provider weight
  updates by hashing a canonical-prompt response.

* `agentnotary guard run -- python my_agent.py` — local HTTP reverse proxy.
  Framework-agnostic. Returns provider-shaped 403s when the agent tries to
  exceed a cost cap, hit a non-allowlisted tool, leak PII, or run away.
  Every observability tool I tried is passive; this one actually intercepts
  at the API boundary.

* `agentnotary compliance --standard eu-ai-act` — generates Annex IV
  technical documentation in Markdown + JSON. Deterministic risk classifier
  (rule engine, not an LLM call); every classification cites the rule that
  fired. EU AI Act enforcement begins Aug 2 2026 — three months out.

* `agentnotary attack --suite owasp-llm-top10` — adversarial fuzzer with
  bundled OWASP LLM Top 10 corpus. Reports per-attack evidence and a
  vulnerability rate. Dry-run mode predicts blockability from declared
  guardrails; live mode (with API key) sends the attacks.

Plus `bom` (CycloneDX/SPDX SBOM), `bench` (cross-model Pareto chart),
and `replay --rewind` (time-travel debugger that forks any session at any
step and simulates forward).

What's intentionally NOT in scope: another tracing dashboard, framework
integrations, anything that needs a SaaS backend. AgentNotary sits
*alongside* LangSmith / Langfuse, not against them. They watch agents.
We certify agents.

169 tests, Apache 2.0, Python 3.9+. The `agent.lock` format is a public
spec — I want it on every agent in production.

Repo: https://github.com/CharanBharathula/agentnotary
Install: pip install agentnotary

Happy to answer questions.
```

**Comment-ready follow-ups (to seed once people start asking):**

- *"Why a proxy and not framework integrations?"* → because the agent is a black box and the API boundary is the only universal interception point. Works with LangChain, CrewAI, AutoGen, raw SDKs, anything that respects `ANTHROPIC_BASE_URL` / `OPENAI_BASE_URL`.

- *"Why was this called agentbox?"* → That name had become synonymous with sandbox/container projects (TwillAI, Dify-AgentBox, multiple recent forks). Different category. Renamed before launch so there's no name confusion.

- *"How is this different from LangSmith?"* → LangSmith is observability — it tells you what happened. AgentNotary is a notary — it produces evidence and enforces policy. Different category, complementary.

- *"Does the EU AI Act compliance generator actually pass an audit?"* → No, and the doc says so prominently. It's a *scaffold* — auditor still needs to review. But it gets the structured fields and citations to the right rules so the auditor isn't starting from a blank page.

---

## 2. LinkedIn post (longer-form, GRC/CISO audience)

```
Three months until EU AI Act enforcement begins (August 2, 2026).

Most of the AI agent governance conversation right now is about
observability — dashboards that tell you what happened after the
fact. But "after the fact" doesn't help the compliance officer who
has to produce Annex IV technical documentation for a notified body.

I built AgentNotary because the missing primitive isn't another
dashboard. It's a notary public for AI agents.

One CLI, eight commands. The three that matter most for compliance:

  ✓ agentnotary seal
    Cryptographic hash of the agent's manifest, prompts, tool source,
    MCP server versions, and dependencies. Detects silent provider
    weight updates via a canonical-prompt probe. Sealed before deploy,
    re-verified in CI. Auditors see an immutable record.

  ✓ agentnotary guard run
    Runtime enforcement via local HTTP proxy. Framework-agnostic. Cost
    caps, iteration caps, tool allowlists, PII redaction — all enforced
    at the API boundary, all logged. Every block becomes evidence.

  ✓ agentnotary compliance --standard eu-ai-act
    Annex IV technical documentation, generated deterministically from
    the manifest + seal + recent sessions. Markdown for engineers, JSON
    for GRC tools (OneTrust, ServiceNow GRC, Drata). The risk classifier
    cites the rule that fired so you can audit the classifier itself.

Plus AI-BOM (CycloneDX 1.6 + SPDX 2.3) for procurement, an OWASP LLM
Top 10 fuzzer for security review, a cross-model Pareto chart for
build/buy decisions, and time-travel debugging for incident response.

Open source, Apache 2.0. Free to use. No SaaS dependency. The
`agent.lock` format is a public spec.

If you're wrestling with AI agent governance ahead of August, take a
look. If it doesn't fit your workflow, tell me what's missing — issues
welcome.

Repo: https://github.com/CharanBharathula/agentnotary
Install: pip install agentnotary

#AIGovernance #EUAIAct #ResponsibleAI #AICompliance #OpenSource
```

---

## 3. X / Twitter thread (short-form, builder audience)

```
1/ Shipped AgentNotary — open-source CLI to notarize, govern, and audit AI agents.

8 commands. Apache 2.0. The four that no observability tool will ever ship 👇

https://github.com/CharanBharathula/agentnotary

2/ `agentnotary seal` — Cargo.lock for AI agents.

Cryptographically hashes manifest + prompts + tool source + deps.

Optional --probe flag detects when a provider silently updates the model
behind the same name. (No other agent tool catches this.)

3/ `agentnotary guard run -- python my_agent.py`

Local HTTP proxy. Framework-agnostic.

Blocks runaway cost, off-allowlist tool calls, and PII leaks at the API
boundary. Returns provider-shaped 403s so your SDK raises naturally.

LangSmith/Langfuse watch. Guard intercepts.

4/ `agentnotary compliance --standard eu-ai-act`

Auto-generates EU AI Act Annex IV technical docs.

Markdown for engineers (committable, diffable). JSON for GRC tools.
Deterministic risk classifier cites the rule that fired.

Aug 2 2026 deadline = burning pull.

5/ `agentnotary attack --suite owasp-llm-top10`

Adversarial fuzzer. Bundled OWASP LLM Top 10 corpus.

Tells you exactly which attacks succeed against your agent and why.

Vulnerability rate as a one-liner output. CI-friendly.

6/ Plus:
• `bom` — AI-BOM (CycloneDX + SPDX)
• `bench` — cross-model Pareto chart
• `replay --rewind` — time-travel debugging; fork any session, edit prompt, simulate forward

7/ pip install agentnotary

169 tests, Python 3.9+, no SaaS dependency.

The `agent.lock` format is a public spec. I want it on every agent in production.

Issues welcome 🤘

https://github.com/CharanBharathula/agentnotary
```

---

## 4. r/LocalLLaMA / r/LangChain post (technical, code-heavy)

**Title:** `[Tool] AgentNotary v0.3 — open-source CLI for AI agent governance (seal, guard, compliance, fuzzer, BOM, bench, time-travel debug)`

**Body:**

```
Wanted to share what I've been building — AgentNotary, an open-source CLI
that does the things every "I'm shipping an LLM agent to production" thread
ends up wishing for.

Eight commands, Apache 2.0, no SaaS. Quick tour:

```bash
$ pip install agentnotary
$ agentnotary init refund-bot && cd refund-bot
$ vim agentnotary.yaml      # declare model, tools, guardrails, compliance
$ agentnotary seal           # writes agent.lock — cryptographic snapshot
$ agentnotary attack         # runs OWASP LLM Top 10 against the agent
$ agentnotary guard run -- python -m my_agent   # runs under enforcement
$ agentnotary compliance --standard eu-ai-act   # generates Annex IV docs
$ agentnotary bom --format cyclonedx            # AI-BOM
$ agentnotary bench --models claude-sonnet-4-5,gpt-4o   # Pareto chart
$ agentnotary replay <id> --rewind --step 7 --edit "what if..."   # time-travel
```

The differentiator is that **guard** is an actual HTTP reverse proxy that
intercepts your agent's LLM calls — it works with LangChain, CrewAI, AutoGen,
or raw SDK calls because everything respects `ANTHROPIC_BASE_URL` /
`OPENAI_BASE_URL`. When a typed guardrail fires (cost cap, tool allowlist,
PII pattern, iteration cap), the proxy returns a provider-shaped 403 so your
SDK raises its native exception class.

Repo: https://github.com/CharanBharathula/agentnotary

Genuinely curious what people would build / break / integrate with. Issues
and PRs welcome.
```

---

## 5. Maintenance: post-launch tasks

Once the posts go out, run:

- [ ] **Star your own repo** (one click — seeds the count)
- [ ] **Pin `pip install agentnotary` instructions** in repo description
- [ ] **Tweet/post once per day** for week 1 with concrete outputs (a sealed lock, an attack report, a Pareto chart)
- [ ] **Archive the old `agentbox` repo** in GitHub Settings → "Archive this repository" (after replacing README with the redirect note)
- [ ] **Optional: publish to PyPI** with `python -m build && twine upload dist/*` (you'll need a PyPI token)
- [ ] **Set up GitHub Pages** on docs/ folder for the landing page
- [ ] **Submit AI-BOM CycloneDX support** to the OWASP CycloneDX repo as a known consumer (gets you cited in their docs)

---

## 6. The numbers to lead with

In any post / pitch deck / interview:

- **169 tests** (the credibility number)
- **3-month EU AI Act enforcement runway** (the urgency number)
- **8 commands** (the breadth number)
- **0 SaaS dependencies** (the trust number)
- **`agent.lock`** (the artifact people will tweet a screenshot of)
