## Summary

<!-- One paragraph: what changes and why. -->

## Type

- [ ] Bug fix
- [ ] New feature
- [ ] Refactor / cleanup
- [ ] Documentation
- [ ] Tests / CI

## Checklist

- [ ] Tests pass: `pytest tests/ -q`
- [ ] Lint clean: `ruff check agentnotary/ tests/`
- [ ] New behavior has a test
- [ ] User-visible changes added to `CHANGELOG.md` under `## [Unreleased]`
- [ ] If a manifest field changed, it's reflected in `generate_default_manifest` and the README
- [ ] If `agent.lock` shape changed, the lockfile `apiVersion` was bumped

## Out-of-scope confirmation

I have read `CONTRIBUTING.md` and confirm this PR strengthens the AgentNotary thesis (declare → seal → enforce → document). It is **not** an observability/dashboarding feature, framework integration, or SaaS dependency.
