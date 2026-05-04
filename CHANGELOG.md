# Changelog

All notable changes to AgentNotary are documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.0] — 2026-05-04

The launch release. Project renamed from `agentbox` to `agentnotary` to reflect the actual product positioning (notary public for AI agents) and to escape a crowded namespace where "agentbox" had become synonymous with sandbox/container projects unrelated to governance.

Four new top-level commands ship in this release.

### Added

- **`agentnotary bom`** — AI Software Bill of Materials.
  - CycloneDX 1.6 (OWASP standard) and SPDX 2.3 (Linux Foundation standard) outputs.
  - Enumerates models, prompts, tools, MCP servers, datasets, and Python dependencies.
  - When `agent.lock` is present, components are anchored by cryptographic hashes from the seal.
  - First mover for AI-BOM in the agent space — pairs with NIST/CISA AI supply-chain guidance.
- **`agentnotary bench`** — Cross-model Pareto comparison.
  - Runs the eval suite against multiple models in parallel.
  - ASCII Pareto chart of cost vs accuracy.
  - Dry-run mode (no API key) projects cost from prompt size + the static pricing table.
  - Default lineup: Sonnet 4.5, GPT-4o, GPT-4o-mini, Gemini 2.5 Flash.
- **`agentnotary attack`** — Adversarial fuzzer.
  - Bundled OWASP LLM Top 10 attack corpus (11 attacks across LLM01/02/06/07/09).
  - Dry-run mode predicts blockability based on declared guardrails.
  - Live mode (with API key) sends attacks to the agent's actual model.
  - Severity-classified report with per-attack evidence.
- **`agentnotary replay <id> --rewind`** — Time-travel debugging.
  - Replay any recorded session step by step.
  - `--rewind --step N --edit '<prompt>'` forks the trajectory at step N, replaces the prompt, and either calls the live LLM (if API key present) or uses a deterministic stand-in.
  - Original session cost preserved; rewind only spends on the diverged turn.
- **48 new tests** (total: 169 from 121).

### Changed

- **Project renamed** `agentbox` → `agentnotary`.
  - PyPI: `pip install agentnotary`
  - CLI: `agentnotary` (replaces `agentbox`)
  - Manifest filename: `agentnotary.yaml` (legacy `agentbox.yaml` still parses with a deprecation warning)
  - State directory: `.agentnotary/` (legacy `.agentbox/` still works)
  - apiVersion: `agentnotary/v0.2` (legacy `agentbox/v0.2` still accepted)
  - Env vars: `AGENTNOTARY_*` (replaces `AGENTBOX_*`)
- **CLI banner** reorganized: `Notarize & Govern` / `Audit & Test (v0.3)` / `Develop` / `Versioning & Observability`.
- **Tagline** updated: *"Notarize, govern, and audit AI agents."*
- **Classifiers** in `pyproject.toml` now include `Topic :: Security` and `Intended Audience :: Legal Industry`.

### Backwards compatibility

- Existing `agentbox.yaml` manifests are read transparently with a one-line stderr deprecation warning.
- `apiVersion: agentbox/v0.2` is still recognized as a v0.2 manifest.
- Existing `.agentbox/` session and version directories continue to be respected when `.agentnotary/` is absent.
- Migration: rename `agentbox.yaml` → `agentnotary.yaml`, optionally update apiVersion. No code changes required for typical agents.

## [0.2.0] — 2026-05-03 (released as `agentbox`)

Three new commands turn AgentNotary from a metadata format into a complete governance loop.

### Added

- **`agentnotary seal`** — cryptographic reproducibility lockfile (`agent.lock`).
  - Hashes manifest, prompts (raw + normalized), tool source code, datasets, and dependencies.
  - Optional `--probe` flag sends a canonical prompt at temperature 0 and hashes the response.
  - `agentnotary seal --verify` exits non-zero on any drift, with a human-readable diff.
  - Honest "non_deterministic" caveats list every source of drift the seal cannot prevent.
- **`agentnotary guard run -- <command>`** — runtime enforcement proxy.
  - Local HTTP reverse proxy that wraps the agent's LLM provider calls.
  - Framework-agnostic: works with anything that respects `ANTHROPIC_BASE_URL` / `OPENAI_BASE_URL`.
  - Enforces typed guardrails: cost cap (per-call + per-session), iteration cap, tool allowlist/denylist, PII redaction, content size, rate limit.
  - Returns provider-shaped 403 errors so the agent's SDK raises naturally.
- **`agentnotary compliance --standard eu-ai-act`** — auto-generated regulatory documentation.
  - Combines manifest + seal + session history into EU AI Act Annex IV technical documentation.
  - Deterministic risk classifier with cited rules.
  - Markdown + JSON output formats.
  - `--check` mode for CI.
- **Manifest schema v0.2** with typed `model`, `guardrails`, `entry_point`, and `compliance` blocks.
- **`pricing.py`** — static USD/1M-token table for top ~20 models.
- 58 new tests (total: 121).
- Apache-2.0 LICENSE, CONTRIBUTING.md, CODE_OF_CONDUCT.md, GitHub issue and PR templates.

### Fixed

- `datetime.utcnow()` deprecation warnings cleared.
- Windows console UTF-8 encoding for the hexagonal logo character.

## [0.1.0] — 2026-05-03 (released as `agentbox`)

Initial public release. Manifest format, evals, sessions, version tagging, codebase scanner.
