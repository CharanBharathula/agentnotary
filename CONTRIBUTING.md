# Contributing to AgentNotary

First — thanks for caring enough to read this. AgentNotary is a small, focused tool aiming to be the **declarative governance spec** for AI agents. We want contributions that strengthen that thesis. PRs that broaden into observability, prompt engineering, or another agent framework will likely get a polite "out of scope."

## Quick start

```bash
git clone https://github.com/CharanBharathula/agentnotary
cd agentnotary
pip install -e ".[dev]"
pytest tests/ -q
ruff check agentnotary/ tests/
```

The full test suite runs in ~3 seconds. Lint runs in <1.

## How we make decisions

1. **Open an issue first** for anything larger than a typo or one-line bug fix. We'd rather discuss the design than rebuild the PR.
2. **Stay on-thesis.** Two questions to ask before opening a PR:
   - Does this strengthen *declare → seal → enforce → document*?
   - Could this be done by an existing observability tool? If yes, AgentNotary shouldn't do it.
3. **Three core commands stay primary.** `seal`, `guard`, `compliance`. Everything else is supporting infrastructure.
4. **The spec is the source of truth.** New runtime behavior generally implies a new manifest field, not the other way around.

## What we'd love help with

- **More compliance standards.** NIST AI RMF and ISO/IEC 42001 templates can reuse the existing `ComplianceContext` plumbing in `agentnotary/compliance/`.
- **PII detection robustness.** Space-separated SSNs, obfuscated emails, more international formats. See `agentnotary/guard/pii.py`.
- **Streaming proxy support.** v0.2 only handles request/response. Streaming SSE is the v0.2.1 milestone.
- **MCP server fingerprinting.** Today we hash by package name + pinned_sha. Hashing the actual server binary or its tool schema would be stronger.
- **Risk classifier rules.** New keyword categories for Annex III high-risk domains, especially in non-US jurisdictions.
- **Pricing data freshness.** A scheduled GitHub Action that bumps `agentnotary/pricing.py` from a public source.

## What's out of scope

- LLM observability dashboards (LangSmith, Langfuse, Helicone already do this well)
- Agent compilation to framework code (`build --target` is on the v0.3 roadmap, but framework churn makes this a tar pit — be ready to defend the design)
- Anything that requires a SaaS backend
- Vendor-specific integrations that don't generalize

## Code style

- Python 3.9+ for the library. The CLI uses 3.9-compatible syntax everywhere.
- `ruff check` is the only linter. We accept its judgment; configure it in `pyproject.toml` if a rule is genuinely wrong.
- Type hints are encouraged but not required. Don't add `Any` to silence mypy.
- Tests use `pytest`. New features need new tests; new bug fixes need a regression test.
- Every public function has a one-line docstring. Long-form documentation goes in module-level comments, not function bodies.

## Commit messages

We write commits that explain *why*, not *what*. Pretend a future engineer is reading the change without context (because they will be).

```
feat(seal): probe-response hash for provider weight drift

Sends a canonical prompt at temperature 0 and hashes the response.
Detects the case where Anthropic / OpenAI silently swap weights
behind the same model name — the single most common cause of
"my agent worked yesterday and broke today" in production.

Probing is opt-in via `agentnotary seal --probe` because it requires
an API call (and thus a key in the env).
```

Conventional Commits (`feat:`, `fix:`, `docs:`, `chore:`, `refactor:`, `test:`) are encouraged but not enforced.

## Pull request checklist

- [ ] Tests pass: `pytest tests/ -q`
- [ ] Lint clean: `ruff check agentnotary/ tests/`
- [ ] New behavior has a new test
- [ ] User-visible changes are noted in `CHANGELOG.md` under `## [Unreleased]`
- [ ] If you added a manifest field, it's documented in the README and the default template (`generate_default_manifest`)
- [ ] If you touched `agent.lock` shape, you bumped the lockfile `apiVersion` and added a migration note

## Releasing (maintainers)

1. Bump version in `agentnotary/__init__.py` and `pyproject.toml`.
2. Move `## [Unreleased]` content to `## [X.Y.Z] — YYYY-MM-DD` in `CHANGELOG.md`.
3. Tag locally: `git tag -a vX.Y.Z -m "vX.Y.Z"`.
4. Push tag: `git push origin vX.Y.Z`.
5. CI builds and publishes the wheel + sdist; create a GitHub release with the changelog excerpt.

## License

By contributing, you agree that your contributions will be licensed under the
[Apache License 2.0](LICENSE).

## Code of Conduct

We follow the [Contributor Covenant](CODE_OF_CONDUCT.md). In short: be excellent
to each other.
