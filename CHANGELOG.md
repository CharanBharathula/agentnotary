# Changelog

All notable changes to AgentBox are documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] — 2026-05-03

The differentiation release. Three new commands turn AgentBox from a metadata format into a complete governance loop: **declare → seal → enforce → document**.

### Added

- **`agentbox seal`** — cryptographic reproducibility lockfile (`agent.lock`).
  - Hashes manifest, prompts (raw + normalized), tool source code, datasets, and dependencies.
  - Optional `--probe` flag sends a canonical prompt at temperature 0 and hashes the response — detects silent provider weight updates.
  - `agentbox seal --verify` exits non-zero on any drift, with a human-readable diff.
  - `agentbox seal diff <other.lock>` compares two seals.
  - Honest "non_deterministic" caveats list every source of drift the seal cannot prevent.
- **`agentbox guard run -- <command>`** — runtime enforcement proxy.
  - Local HTTP reverse proxy that wraps the agent's LLM provider calls.
  - Framework-agnostic: works with anything that respects `ANTHROPIC_BASE_URL` / `OPENAI_BASE_URL`.
  - Enforces typed guardrails: cost cap (per-call + per-session), iteration cap, tool allowlist/denylist, PII redaction, content size, rate limit.
  - Returns provider-shaped 403 errors so the agent's SDK raises naturally.
  - Optional Presidio NER PII detection via `pip install agentbox[pii]`.
- **`agentbox compliance --standard eu-ai-act`** — auto-generated regulatory documentation.
  - Combines manifest + seal + session history into EU AI Act Annex IV technical documentation.
  - Deterministic risk classifier with cited rules (Article 5 prohibited / Annex III high-risk / Article 52 transparency / minimal).
  - Markdown output for engineers (committable, diffable in PRs); JSON output for GRC tools (OneTrust, ServiceNow GRC, Drata).
  - `--check` mode for CI: exits non-zero if compliance metadata is missing.
  - Prominent "scaffold only — not legal advice" disclaimer in every generated document.
- **Manifest schema v0.2** (`apiVersion: agentbox/v0.2`).
  - Typed `model:` block (provider, name, pinned_version, temperature, max_tokens).
  - Typed `guardrails:` block (cost, iterations, tools, pii, content, rate) — enforceable, not just metadata.
  - `entry_point:` block — wrapped by `agentbox guard run`.
  - `compliance:` block — risk_class, data_handling, human_oversight, affected_users, intended_purpose, out_of_scope.
  - `compile`, `simulate`, `drift` namespaces reserved for v0.3.
- **`agentbox/pricing.py`** — static USD/1M-token pricing table for the top ~20 models across Anthropic, OpenAI, Google, and local providers.
- 58 new tests (total: 121 from 63), covering seal fingerprinting, lockfile diffing, policy engine, PII detector, risk classifier, compliance generation, and the v0.2 manifest schema.
- Open-source readiness: `LICENSE` (Apache-2.0), `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `CHANGELOG.md`, GitHub issue and PR templates.

### Changed

- **CLI usage banner** reorganized into Govern / Develop / Versioning / Observe sections.
- **`agentbox info` and `agentbox validate`** now correctly count typed v0.2 guardrails (e.g. `5 typed (cost, iterations, tools, pii, rate)`) instead of reporting 0.
- **`generate_default_manifest`** now produces a v0.2 manifest with typed guardrails, compliance metadata, and an entry point.
- **`pyproject.toml`** adds `aiohttp` and `jinja2` to base dependencies; new `[pii]` and `[pdf]` extras.
- Tagline shifted from "Docker for AI Agents" to **"The declarative governance spec for AI agents"** to better reflect the Terraform-style positioning.

### Fixed

- `datetime.utcnow()` deprecation warnings replaced with timezone-aware `datetime.now(timezone.utc)`.
- Windows console UTF-8 encoding issue with the hexagonal logo character (`⬡`) — `cli.py` now reconfigures stdout to UTF-8 on Windows.
- v0.1 manifests with free-form list-style guardrails continue to parse cleanly under v0.2 (one-line stderr deprecation note instead of an error).

### Backwards compatibility

All v0.1 manifests parse without modification under v0.2. New typed features activate only when `apiVersion: agentbox/v0.2` is set at the top of the manifest. The legacy `Guardrail` / flat-model fields remain on `AgentManifest` and are populated for both forms.

## [0.1.0] — 2026-05-03

Initial public release. Manifest format, evals, sessions, version tagging, codebase scanner.
