#!/usr/bin/env python3
"""
AgentNotary CLI
============
Docker for AI Agents. Package, test, version, and deploy AI agents.

Usage:
    agentnotary init [name]          Create a new agent project
    agentnotary validate             Validate the current agent manifest
    agentnotary test                 Run eval suite against the agent
    agentnotary record <input>       Run agent and record the session
    agentnotary replay <session-id>  Replay a recorded session
    agentnotary sessions             List recorded sessions
    agentnotary tag <version>        Tag current state as a version
    agentnotary versions             List all tagged versions
    agentnotary rollback <version>   Rollback to a tagged version
    agentnotary scan [directory]     Scan for agents in a codebase
    agentnotary info                 Show current agent info
"""

import os
import sys
from pathlib import Path

# Ensure Unicode output works on Windows terminals
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


# ── Formatting helpers ────────────────────────────────────────────────────────

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
CYAN = "\033[96m"
DIM = "\033[2m"
BOLD = "\033[1m"
RESET = "\033[0m"


def print_header(text):
    print(f"\n{BOLD}{CYAN}⬡ AgentNotary{RESET} {DIM}— {text}{RESET}\n")


def print_success(text):
    print(f"  {GREEN}✓{RESET} {text}")


def print_error(text):
    print(f"  {RED}✗{RESET} {text}")


def print_warn(text):
    print(f"  {YELLOW}!{RESET} {text}")


def print_info(text):
    print(f"  {BLUE}→{RESET} {text}")


def print_dim(text):
    print(f"  {DIM}{text}{RESET}")


def print_table(headers, rows):
    """Print a simple aligned table."""
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(str(cell)))

    header_str = "  ".join(f"{h:<{widths[i]}}" for i, h in enumerate(headers))
    print(f"  {DIM}{header_str}{RESET}")
    print(f"  {DIM}{'─' * (sum(widths) + 2 * (len(widths) - 1))}{RESET}")
    for row in rows:
        row_str = "  ".join(f"{str(c):<{widths[i]}}" for i, c in enumerate(row))
        print(f"  {row_str}")


# ── Helpers ───────────────────────────────────────────────────────────────────


def _count_guardrails(manifest) -> str:
    """Human-friendly guardrail count for v0.1 (legacy list) and v0.2 (typed spec)."""
    if manifest.guardrail_spec is not None:
        spec = manifest.guardrail_spec
        active = []
        if spec.cost.max_usd_per_session is not None or spec.cost.max_usd_per_call is not None:
            active.append("cost")
        if spec.iterations.max_llm_calls is not None or spec.iterations.max_tool_calls is not None:
            active.append("iterations")
        if spec.tools.allowlist or spec.tools.denylist or spec.tools.require_approval:
            active.append("tools")
        if spec.pii.patterns or spec.pii.action != "redact":
            active.append("pii")
        if spec.content.max_input_tokens is not None or spec.content.blocked_phrases_file:
            active.append("content")
        if spec.rate.max_calls_per_minute is not None or spec.rate.max_calls_per_session is not None:
            active.append("rate")
        if active:
            return f"{len(active)} typed ({', '.join(active)})"
        return "0 (typed block declared but empty)"
    return str(len(manifest.guardrails))


# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_init(args):
    """Initialize a new agent project."""
    from agentnotary.manifest import generate_default_manifest, generate_eval_template

    name = args[0] if args else "my-agent"
    print_header(f"Initializing agent: {name}")

    # Create manifest
    manifest_path = Path("agentnotary.yaml")
    if manifest_path.exists():
        print_warn("agentnotary.yaml already exists. Skipping.")
    else:
        manifest_path.write_text(generate_default_manifest(name), encoding="utf-8")
        print_success("Created agentnotary.yaml")

    # Create directories
    for d in ["prompts", "evals", ".agentnotary/sessions", ".agentnotary/versions"]:
        Path(d).mkdir(parents=True, exist_ok=True)

    # Create eval template
    eval_path = Path("evals/test_suite.yaml")
    if not eval_path.exists():
        eval_path.write_text(generate_eval_template(), encoding="utf-8")
        print_success("Created evals/test_suite.yaml")

    # Create .gitignore
    gitignore = Path(".agentnotary/.gitignore")
    if not gitignore.exists():
        gitignore.write_text("sessions/\n", encoding="utf-8")
        print_success("Created .agentnotary/.gitignore")

    print()
    print_info("Edit agentnotary.yaml to configure your agent")
    print_info(f"Run {BOLD}agentnotary test{RESET} to evaluate")
    print_info(f"Run {BOLD}agentnotary tag v0.1.0{RESET} to save a version")
    print()


def cmd_validate(args):
    """Validate the current manifest."""
    from agentnotary.manifest import parse_manifest, validate_manifest

    print_header("Validating agent manifest")

    try:
        manifest = parse_manifest(".")
    except (FileNotFoundError, ValueError) as e:
        print_error(str(e))
        return 1

    issues = validate_manifest(manifest)

    print_info(f"Agent: {BOLD}{manifest.name}{RESET} v{manifest.version}")
    print_info(f"Model: {manifest.effective_model}")
    print_info(f"Framework: {manifest.framework}")
    print_info(f"Tools: {len(manifest.tools)}")
    print_info(f"Guardrails: {_count_guardrails(manifest)}")
    print_info(f"Memory: {manifest.memory}")
    print()

    if not issues:
        print_success("Manifest is valid. No issues found.")
    else:
        for issue in issues:
            if issue.startswith("ERROR"):
                print_error(issue)
            elif issue.startswith("WARNING"):
                print_warn(issue)
            else:
                print_dim(issue)

    return 0


def cmd_test(args):
    """Run eval suite against the agent."""
    from agentnotary.manifest import parse_manifest
    from agentnotary.tester import AgentTestRunner

    print_header("Running eval suite")

    try:
        manifest = parse_manifest(".")
    except (FileNotFoundError, ValueError) as e:
        print_error(str(e))
        return 1

    eval_path = manifest.eval_suite or "./evals/test_suite.yaml"
    if not Path(eval_path).exists():
        print_error(f"Eval suite not found: {eval_path}")
        print_info("Run 'agentnotary init' to create a default eval suite")
        return 1

    print_info(f"Agent: {manifest.name} v{manifest.version}")
    print_info(f"Model: {manifest.model}")
    print_info(f"Suite: {eval_path}")
    print()

    runner = AgentTestRunner(manifest, verbose="--verbose" in args)
    results = runner.run_suite(eval_path)

    # Display results
    rows = []
    for r in results["results"]:
        status_icon = {
            "passed": f"{GREEN}PASS{RESET}",
            "failed": f"{RED}FAIL{RESET}",
            "error": f"{RED}ERR {RESET}",
            "skipped": f"{DIM}SKIP{RESET}",
        }.get(r["status"], r["status"])

        row = [
            status_icon,
            r["name"],
            f"{r['latency_ms']}ms" if r["latency_ms"] else "-",
            f"${r['cost_usd']:.4f}" if r["cost_usd"] else "-",
            r["failure_reason"][:40] if r["failure_reason"] else "",
        ]
        rows.append(row)

    print_table(["STATUS", "TEST", "LATENCY", "COST", "REASON"], rows)

    print()
    pass_color = GREEN if results["failed"] == 0 else RED
    print(f"  {pass_color}{BOLD}{results['pass_rate']} pass rate{RESET}  "
          f"{results['passed']} passed · {results['failed']} failed · "
          f"{results['errors']} errors · {results['skipped']} skipped")
    print(f"  Total cost: ${results['total_cost_usd']:.4f}  "
          f"Avg latency: {results['avg_latency_ms']}ms")
    print()

    return 0 if results["failed"] == 0 else 1


def cmd_sessions(args):
    """List recorded sessions."""
    from agentnotary.recorder import list_sessions

    print_header("Recorded sessions")

    sessions = list_sessions(".")
    if not sessions:
        print_dim("No sessions recorded yet. Run 'agentnotary record' to start.")
        return

    rows = []
    for s in sessions[:20]:
        status_color = GREEN if s["status"] == "completed" else RED
        rows.append([
            s["session_id"],
            s["agent_name"],
            s["version"],
            f"{status_color}{s['status']}{RESET}",
            f"${s['cost']:.4f}",
            f"{s['tokens']}",
            f"{s['tools_called']}",
            s["started_at"][:19],
        ])

    print_table(
        ["ID", "AGENT", "VER", "STATUS", "COST", "TOKENS", "TOOLS", "STARTED"],
        rows
    )
    print()


def cmd_tag(args):
    """Tag current state as a version."""
    from agentnotary.versioner import tag_version

    if not args:
        print_error("Usage: agentnotary tag <version>  (e.g., agentnotary tag v1.0.0)")
        return 1

    version = args[0]
    print_header(f"Tagging version: {version}")

    try:
        meta = tag_version(version, ".")
        print_success(f"Tagged {version}")
        print_info(f"Hash: {meta['manifest_hash']}")
        print_info(f"Time: {meta['tagged_at']}")
        print()
        print_info(f"Rollback with: {BOLD}agentnotary rollback {version}{RESET}")
    except ValueError as e:
        print_error(str(e))
        return 1

    return 0


def cmd_versions(args):
    """List all tagged versions."""
    from agentnotary.versioner import list_versions

    print_header("Tagged versions")

    versions = list_versions(".")
    if not versions:
        print_dim("No versions tagged yet. Run 'agentnotary tag v0.1.0' to start.")
        return

    rows = []
    for v in versions:
        rows.append([
            v.get("version", "?"),
            v.get("tagged_at", "unknown")[:19],
            v.get("manifest_hash", "")[:12],
        ])

    print_table(["VERSION", "TAGGED AT", "HASH"], rows)
    print()


def cmd_rollback(args):
    """Rollback to a tagged version."""
    from agentnotary.versioner import rollback_to

    if not args:
        print_error("Usage: agentnotary rollback <version>")
        return 1

    print_header(f"Rolling back to: {args[0]}")

    try:
        result = rollback_to(args[0], ".")
        print_success(f"Rolled back to {result['rolled_back_to']}")
        print_info("Current state was auto-saved before rollback")
    except FileNotFoundError as e:
        print_error(str(e))
        return 1

    return 0


def cmd_scan(args):
    """Scan a directory for AI agents."""
    from agentnotary.scanner import format_scan_results, scan_directory

    target = args[0] if args else "."
    print_header(f"Scanning for agents in: {os.path.abspath(target)}")

    agents, files_scanned = scan_directory(target)
    report = format_scan_results(agents, files_scanned)

    print_info(f"Files scanned: {report['files_scanned']}")
    print_info(f"Agents found: {report['total_agents_found']}")
    print()

    if not report["agents"]:
        print_dim("No agents detected.")
        return

    # Framework breakdown
    print(f"  {BOLD}Frameworks:{RESET}")
    for fw, count in report["frameworks"].items():
        print(f"    {fw}: {count}")
    print()

    # Risk summary
    ungoverned = report["ungoverned_agents"]
    if ungoverned > 0:
        print_warn(f"{ungoverned} agents have NO guardrails")
    else:
        print_success("All agents have guardrails defined")
    print()

    # Agent list
    rows = []
    for a in report["agents"]:
        guardrail_icon = f"{GREEN}✓{RESET}" if a["guardrails"] else f"{RED}✗{RESET}"
        rows.append([
            a["framework"],
            a["model"][:25],
            "✓" if a["tools"] else "-",
            guardrail_icon,
            "✓" if a["memory"] else "-",
            a["confidence"],
            f"{a['file']}:{a['line']}",
        ])

    print_table(
        ["FRAMEWORK", "MODEL", "TOOLS", "GUARD", "MEM", "CONF", "LOCATION"],
        rows
    )
    print()


def cmd_info(args):
    """Show current agent info."""
    from agentnotary.manifest import parse_manifest

    print_header("Agent Info")

    try:
        manifest = parse_manifest(".")
    except (FileNotFoundError, ValueError) as e:
        print_error(str(e))
        return 1

    print(f"  {BOLD}Name:{RESET}        {manifest.name}")
    print(f"  {BOLD}Version:{RESET}     {manifest.version}")
    print(f"  {BOLD}Description:{RESET} {manifest.description}")
    print(f"  {BOLD}Framework:{RESET}   {manifest.framework}")
    print(f"  {BOLD}Model:{RESET}       {manifest.effective_model}")
    print(f"  {BOLD}Temp:{RESET}        {manifest.temperature}")
    print(f"  {BOLD}Memory:{RESET}      {manifest.memory}")
    print(f"  {BOLD}Tools:{RESET}       {len(manifest.tools)}")
    print(f"  {BOLD}Guardrails:{RESET}  {_count_guardrails(manifest)}")
    print(f"  {BOLD}Tags:{RESET}        {', '.join(manifest.tags) if manifest.tags else 'none'}")
    print(f"  {BOLD}Author:{RESET}      {manifest.author or 'not set'}")

    if manifest.system_prompt:
        preview = manifest.system_prompt[:100].replace('\n', ' ')
        print(f"  {BOLD}Prompt:{RESET}      {DIM}{preview}...{RESET}")

    print()
    return 0


# ── v0.2 commands: seal, guard, compliance ─────────────────────────────────────

def cmd_seal(args):
    """Generate or verify agent.lock — cryptographic reproducibility seal."""
    from agentnotary.seal import diff_seals, load_lock, seal_agent, verify_seal, write_lock

    if args and args[0] == "--verify":
        print_header("Verifying agent.lock")
        result = verify_seal(".")
        if result.ok:
            print_success(result.summary)
            return 0
        print_error(result.summary)
        for d in result.diffs[:20]:
            kind_colors = {"added": GREEN, "removed": RED, "changed": YELLOW}
            color = kind_colors.get(d.kind, DIM)
            print(f"  {color}{d.kind:>8}{RESET} {d.path}")
            if d.before is not None:
                print(f"           {DIM}before:{RESET} {(d.before or '')[:80]}")
            if d.after is not None:
                print(f"           {DIM}after: {RESET} {(d.after or '')[:80]}")
        if len(result.diffs) > 20:
            print_dim(f"  ... and {len(result.diffs) - 20} more changes")
        return 1

    if args and args[0] == "diff" and len(args) >= 2:
        print_header(f"Diffing agent.lock vs {args[1]}")
        a = load_lock(".")
        from pathlib import Path
        other_dir = Path(args[1]).parent if Path(args[1]).is_file() else Path(args[1])
        b = load_lock(str(other_dir))
        diffs = diff_seals(a, b)
        if not diffs:
            print_success("No differences.")
            return 0
        for d in diffs:
            color = {"added": GREEN, "removed": RED, "changed": YELLOW}.get(d.kind, DIM)
            print(f"  {color}{d.kind:>8}{RESET} {d.path}")
            if d.before is not None:
                print(f"           {DIM}before:{RESET} {(d.before or '')[:80]}")
            if d.after is not None:
                print(f"           {DIM}after: {RESET} {(d.after or '')[:80]}")
        return 0

    probe = "--probe" in args
    print_header("Sealing agent" + (" (with provider probe)" if probe else ""))
    try:
        lock = seal_agent(".", probe=probe)
        path = write_lock(lock, ".")
    except FileNotFoundError as e:
        print_error(str(e))
        return 1

    print_success(f"Wrote {path.name}")
    print_info(f"Seal hash:    {lock.seal_hash[:24]}...")
    print_info(f"Manifest:     {lock.manifest.get('sha256', '')[:24]}...")
    print_info(f"Prompts:      {len(lock.prompts)}")
    print_info(f"Tools:        {len(lock.tools)}")
    print_info(f"Datasets:     {len(lock.datasets)}")
    if lock.model.get("probe_response_hash"):
        print_info(f"Probe hash:   {lock.model['probe_response_hash'][:24]}...")
    elif lock.model.get("probe_skipped_reason"):
        print_dim(f"  Probe: {lock.model['probe_skipped_reason']}")
    if lock.non_deterministic:
        print()
        print_warn(f"{len(lock.non_deterministic)} non-determinism caveat(s) recorded:")
        for n in lock.non_deterministic[:3]:
            print(f"    {DIM}- {n[:100]}...{RESET}")
        if len(lock.non_deterministic) > 3:
            print_dim(f"    ... and {len(lock.non_deterministic) - 3} more (see agent.lock)")
    print()
    print_info(f"Verify with: {BOLD}agentnotary seal --verify{RESET}")
    print()
    return 0


def cmd_guard(args):
    """Run an agent under runtime governance — blocks runaway loops, enforces caps."""
    from agentnotary.guard import run_under_guard
    from agentnotary.manifest import parse_manifest

    if not args or args[0] != "run":
        print_error("Usage: agentnotary guard run -- <command> [args...]")
        print_info("Example: agentnotary guard run -- python -m my_agent")
        return 1

    # Strip the optional "--" separator
    cmd_args = args[1:]
    if cmd_args and cmd_args[0] == "--":
        cmd_args = cmd_args[1:]

    if not cmd_args:
        print_error("Missing agent command after `agentnotary guard run --`.")
        return 1

    print_header(f"Guard: wrapping {' '.join(cmd_args)}")
    try:
        manifest = parse_manifest(".")
    except (FileNotFoundError, ValueError) as e:
        print_error(str(e))
        return 1

    if not manifest.guardrail_spec:
        print_warn("No typed guardrails declared. Guard will record but not enforce.")
        print_info(f"Add typed guardrails to agentnotary.yaml — see {BOLD}agentnotary info{RESET}")

    result = run_under_guard(manifest, cmd_args, base_dir=".")

    print()
    if result.blocked:
        print_error(f"Guard BLOCKED the agent: {result.block_reason}")
    else:
        print_success(f"Agent exited with code {result.exit_code}")

    s = result.summary
    print_info(f"Session:        {result.session_id}")
    print_info(f"LLM calls:      {s.get('llm_calls', 0)}")
    print_info(f"Tool calls:     {s.get('tool_calls', 0)}")
    print_info(f"Total cost:     ${s.get('session_cost_usd', 0):.4f}")
    print_info(f"Duration:       {s.get('session_seconds', 0):.1f}s")
    print()
    return result.exit_code


def cmd_compliance(args):
    """Generate regulatory compliance documentation from manifest + seal + sessions."""
    from agentnotary.compliance import check, generate
    from agentnotary.manifest import parse_manifest

    standard = "eu-ai-act"
    output = "./compliance"
    fmt = "all"
    check_only = False

    i = 0
    while i < len(args):
        a = args[i]
        if a == "--standard" and i + 1 < len(args):
            standard = args[i + 1]
            i += 2
        elif a == "--output" and i + 1 < len(args):
            output = args[i + 1]
            i += 2
        elif a == "--format" and i + 1 < len(args):
            fmt = args[i + 1]
            i += 2
        elif a == "--check":
            check_only = True
            i += 1
        else:
            print_error(f"Unknown flag: {a}")
            return 1

    print_header(f"Compliance: {standard}")

    try:
        manifest = parse_manifest(".")
    except (FileNotFoundError, ValueError) as e:
        print_error(str(e))
        return 1

    if check_only:
        issues = check(manifest)
        if not issues:
            print_success("Manifest has all required fields for compliance generation.")
            return 0
        errors = [i for i in issues if i.severity == "error"]
        for issue in issues:
            if issue.severity == "error":
                print_error(f"{issue.field}: {issue.message}")
            elif issue.severity == "warning":
                print_warn(f"{issue.field}: {issue.message}")
            else:
                print_dim(f"  {issue.field}: {issue.message}")
        return 1 if errors else 0

    try:
        result = generate(".", standard, output, format=fmt)
    except ValueError as e:
        print_error(str(e))
        return 1

    print_info(f"Risk class: {BOLD}{result.risk.risk_class.upper()}{RESET}")
    print_dim(f"  {result.risk.summary}")
    print()
    for f in result.files_written:
        print_success(f"Wrote {f}")
    if result.issues:
        print()
        for issue in result.issues:
            if issue.severity == "error":
                print_error(f"{issue.field}: {issue.message}")
            elif issue.severity == "warning":
                print_warn(f"{issue.field}: {issue.message}")
    print()
    print_warn("Documentation is a SCAFFOLD ONLY — review by qualified counsel required.")
    print()
    return 0


# ── v0.3 commands: bom, bench, attack, rewind ─────────────────────────────────


def cmd_bom(args):
    """Generate AI Software Bill of Materials (CycloneDX or SPDX)."""
    from agentnotary.bom import SUPPORTED_BOM_FORMATS, write_bom

    fmt = "cyclonedx"
    output = None
    i = 0
    while i < len(args):
        if args[i] == "--format" and i + 1 < len(args):
            fmt = args[i + 1]
            i += 2
        elif args[i] in ("-o", "--output") and i + 1 < len(args):
            output = args[i + 1]
            i += 2
        else:
            print_error(f"Unknown flag: {args[i]}")
            return 1
    if fmt not in SUPPORTED_BOM_FORMATS:
        print_error(f"Unknown format '{fmt}'. Supported: {', '.join(SUPPORTED_BOM_FORMATS)}")
        return 1

    print_header(f"Generating AI-BOM ({fmt})")
    try:
        path = write_bom(".", format=fmt, output_path=output)
    except (FileNotFoundError, ValueError) as e:
        print_error(str(e))
        return 1
    print_success(f"Wrote {path}")
    print_info(f"Format: {fmt} ({'OWASP CycloneDX 1.6' if fmt == 'cyclonedx' else 'SPDX 2.3'})")
    print_info("Pair with `agentnotary seal` for cryptographically-anchored BOM components")
    print()
    return 0


def cmd_bench(args):
    """Cross-model Pareto comparison: cost vs accuracy."""
    from agentnotary.bench import pareto_chart, run_bench

    models = []
    eval_path = None
    dry_run = None
    i = 0
    while i < len(args):
        if args[i] in ("-m", "--models") and i + 1 < len(args):
            models = [m.strip() for m in args[i + 1].split(",") if m.strip()]
            i += 2
        elif args[i] in ("-e", "--eval") and i + 1 < len(args):
            eval_path = args[i + 1]
            i += 2
        elif args[i] == "--dry-run":
            dry_run = True
            i += 1
        elif args[i] == "--live":
            dry_run = False
            i += 1
        else:
            print_error(f"Unknown flag: {args[i]}")
            return 1

    print_header("Bench: cross-model Pareto")
    try:
        result = run_bench(".", models or None, eval_path=eval_path, dry_run=dry_run)
    except (FileNotFoundError, ValueError) as e:
        print_error(str(e))
        return 1

    if result.dry_run:
        print_warn("DRY-RUN: no API key in env. Cost projected from prompt size + pricing table.")
        print_dim("Set ANTHROPIC_API_KEY or OPENAI_API_KEY for measured pass-rates.")
    print_info(f"Eval suite: {result.eval_path}")
    print_info(f"Cases: {result.n_cases}")
    print()
    print(pareto_chart(result))
    print()
    return 0


def cmd_attack(args):
    """Adversarial fuzzer — runs OWASP LLM Top 10 attacks against the agent."""
    from agentnotary.attack import SUPPORTED_SUITES, run_attacks

    suite = "owasp-llm-top10"
    live = None
    i = 0
    while i < len(args):
        if args[i] == "--suite" and i + 1 < len(args):
            suite = args[i + 1]
            i += 2
        elif args[i] == "--live":
            live = True
            i += 1
        elif args[i] == "--dry-run":
            live = False
            i += 1
        else:
            print_error(f"Unknown flag: {args[i]}")
            return 1
    if suite not in SUPPORTED_SUITES:
        print_error(f"Unknown suite '{suite}'. Supported: {', '.join(SUPPORTED_SUITES)}")
        return 1

    print_header(f"Attack: {suite}")
    try:
        report = run_attacks(".", suite=suite, live=live)
    except (FileNotFoundError, ValueError) as e:
        print_error(str(e))
        return 1

    if report.dry_run:
        print_warn("DRY-RUN: predicted vulnerability based on declared guardrails. "
                    "Set an API key + use --live for measured results.")

    rate = report.vulnerability_rate * 100
    color = GREEN if rate < 20 else (YELLOW if rate < 50 else RED)
    print_info(f"Suite: {report.suite}")
    print_info(f"Total attacks: {report.total_attacks}")
    print(f"  {color}{BOLD}{rate:.0f}% vulnerability rate{RESET}  "
           f"{report.successful_attacks} succeeded · {report.blocked_attacks} blocked")
    print()

    rows = []
    for r in report.results:
        status = (f"{RED}VULN{RESET}" if r.succeeded else f"{GREEN}SAFE{RESET}")
        rows.append([
            status,
            r.case.severity[:4].upper(),
            r.case.id,
            r.case.title[:50],
            r.evidence[:50] if r.evidence else "",
        ])
    print_table(["", "SEV", "ID", "ATTACK", "EVIDENCE"], rows)
    print()

    crit = report.by_severity("critical")
    high = report.by_severity("high")
    if crit or high:
        print_warn(f"{len(crit)} critical + {len(high)} high-severity attacks succeeded.")
        print_info("Strengthen system_prompt, add typed PII guardrails, restrict tool allowlist.")
    print()
    return 1 if report.successful_attacks else 0


def cmd_replay(args):
    """Replay a recorded session (with optional --rewind to fork at a step)."""
    from agentnotary.recorder import load_session
    from agentnotary.rewind import rewind_session

    if not args:
        print_error("Usage: agentnotary replay <session-id> [--rewind --step N --edit '<prompt>']")
        return 1

    session_id = args[0]
    rewind = False
    step = None
    edit_prompt = None
    i = 1
    while i < len(args):
        a = args[i]
        if a == "--rewind":
            rewind = True
            i += 1
        elif a == "--step" and i + 1 < len(args):
            step = int(args[i + 1])
            i += 2
        elif a == "--edit" and i + 1 < len(args):
            edit_prompt = args[i + 1]
            i += 2
        else:
            print_error(f"Unknown flag: {a}")
            return 1

    if not rewind:
        # Plain replay: print every action like before
        print_header(f"Replaying session: {session_id}")
        try:
            session = load_session(session_id, ".")
        except FileNotFoundError as e:
            print_error(str(e))
            return 1

        print_info(f"Agent: {session['agent_name']} v{session['agent_version']}")
        print_info(f"Model: {session['model']}")
        print_info(f"Status: {session['status']}")
        print_info(f"Cost:  ${session['total_cost_usd']:.4f}")
        print()
        for i, action in enumerate(session.get("actions", []), 1):
            atype = action["action_type"]
            icon = {"llm_call": "🤖", "tool_call": "🔧", "decision": "💡",
                    "guardrail_triggered": "🛡", "error": "❌"}.get(atype, "  ")
            line = f"  [{i}] {icon} {BOLD}{atype}{RESET}"
            if action.get("duration_ms"):
                line += f" {DIM}({action['duration_ms']}ms){RESET}"
            if action.get("cost_usd"):
                line += f" {DIM}(${action['cost_usd']:.4f}){RESET}"
            print(line)
            for k, v in (action.get("content") or {}).items():
                print(f"      {DIM}{k}: {str(v)[:80]}{RESET}")
        print()
        return 0

    # Rewind mode
    print_header(f"Rewinding session: {session_id}")
    try:
        result = rewind_session(session_id, ".", fork_step=step, edit_prompt=edit_prompt)
    except (FileNotFoundError, IndexError) as e:
        print_error(str(e))
        return 1

    if step:
        print_info(f"Fork point: step {step}")
    if edit_prompt:
        print_info(f"Edited prompt: {edit_prompt[:80]}...")
    if result.used_live_llm:
        print_success("Diverged turn sent to live LLM.")
    elif edit_prompt:
        print_warn("No API key in env — diverged turn used a deterministic stand-in.")
    print_info(f"Original session cost: ${result.original_total_cost_usd:.4f}")
    if result.rewind_total_cost_usd:
        print_info(f"Rewind incremental cost: ${result.rewind_total_cost_usd:.4f}")
    print()

    for s in result.steps:
        marker = ""
        if s.is_fork_point:
            marker = f"{YELLOW}◆ FORK{RESET}"
        elif s.is_simulated:
            marker = f"{DIM}~ sim{RESET}"
        print(f"  [{s.index:>3}] {marker:<14} {s.summary}")

    if result.notes:
        print()
        for n in result.notes:
            print_dim(f"  {n}")
    print()
    return 0


# ── Main ──────────────────────────────────────────────────────────────────────

COMMANDS = {
    "init": cmd_init,
    "validate": cmd_validate,
    "test": cmd_test,
    "sessions": cmd_sessions,
    "replay": cmd_replay,
    "tag": cmd_tag,
    "versions": cmd_versions,
    "rollback": cmd_rollback,
    "scan": cmd_scan,
    "info": cmd_info,
    # v0.2 — the differentiated wedge
    "seal": cmd_seal,
    "guard": cmd_guard,
    "compliance": cmd_compliance,
    # v0.3 — the attention-grabbing suite
    "bom": cmd_bom,
    "bench": cmd_bench,
    "attack": cmd_attack,
}


def print_usage():
    print(f"""
{BOLD}{CYAN}⬡ AgentNotary{RESET} — Notarize, govern, and audit AI agents
{DIM}Notarize → Enforce → Certify.{RESET}

{BOLD}Usage:{RESET}
  agentnotary <command> [options]

{BOLD}Notarize & Govern:{RESET}
  {GREEN}seal{RESET} [--probe]           Cryptographic seal (agent.lock)
  {GREEN}seal --verify{RESET}            Verify nothing has drifted since the last seal
  {GREEN}guard run -- <cmd>{RESET}       Run an agent under runtime enforcement
  {GREEN}compliance{RESET} [--check]     Generate EU AI Act / regulatory docs

{BOLD}Audit & Test (v0.3):{RESET}
  {GREEN}bom{RESET} [--format ...]       AI Software Bill of Materials (CycloneDX/SPDX)
  {GREEN}bench{RESET} [--models ...]     Cross-model Pareto: cost vs accuracy
  {GREEN}attack{RESET} [--suite ...]     Adversarial fuzzer (OWASP LLM Top 10)
  {GREEN}replay{RESET} <id> --rewind     Time-travel debug — fork at step N

{BOLD}Develop:{RESET}
  {GREEN}init{RESET} [name]              Create a new agent project
  {GREEN}validate{RESET}                 Validate agent manifest
  {GREEN}test{RESET} [--verbose]         Run eval suite
  {GREEN}info{RESET}                     Show current agent details

{BOLD}Versioning & Observability:{RESET}
  {GREEN}tag{RESET} <version>            Tag current state (e.g., v1.0.0)
  {GREEN}versions{RESET} / {GREEN}rollback{RESET}    List or restore tagged versions
  {GREEN}sessions{RESET} / {GREEN}replay{RESET} <id> List or replay recorded sessions
  {GREEN}scan{RESET} [directory]         Discover agents in codebase

{BOLD}Get started:{RESET}
  agentnotary init my-agent
  cd my-agent
  agentnotary seal                                    # notarize
  agentnotary guard run -- python my_agent.py         # enforce
  agentnotary compliance --standard eu-ai-act         # certify
  agentnotary attack --suite owasp-llm-top10          # adversarial test
  agentnotary bom --format cyclonedx                  # AI-BOM

{DIM}https://github.com/CharanBharathula/agentnotary{RESET}
""")


def main():
    args = sys.argv[1:]

    if not args or args[0] in ("-h", "--help", "help"):
        print_usage()
        return 0

    command = args[0]
    cmd_args = args[1:]

    if command not in COMMANDS:
        print_error(f"Unknown command: {command}")
        print_usage()
        return 1

    try:
        return COMMANDS[command](cmd_args) or 0
    except KeyboardInterrupt:
        print("\n  Interrupted.")
        return 130
    except Exception as e:
        print_error(f"Error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
