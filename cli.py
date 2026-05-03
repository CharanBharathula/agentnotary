#!/usr/bin/env python3
"""
AgentBox CLI
============
Docker for AI Agents. Package, test, version, and deploy AI agents.

Usage:
    agentbox init [name]          Create a new agent project
    agentbox validate             Validate the current agent manifest
    agentbox test                 Run eval suite against the agent
    agentbox record <input>       Run agent and record the session
    agentbox replay <session-id>  Replay a recorded session
    agentbox sessions             List recorded sessions
    agentbox tag <version>        Tag current state as a version
    agentbox versions             List all tagged versions
    agentbox rollback <version>   Rollback to a tagged version
    agentbox scan [directory]     Scan for agents in a codebase
    agentbox info                 Show current agent info
"""

import sys
import os
import json
from pathlib import Path


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
    print(f"\n{BOLD}{CYAN}⬡ AgentBox{RESET} {DIM}— {text}{RESET}\n")


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


# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_init(args):
    """Initialize a new agent project."""
    from agentbox.manifest import generate_default_manifest, generate_eval_template

    name = args[0] if args else "my-agent"
    print_header(f"Initializing agent: {name}")

    # Create manifest
    manifest_path = Path("agentbox.yaml")
    if manifest_path.exists():
        print_warn("agentbox.yaml already exists. Skipping.")
    else:
        manifest_path.write_text(generate_default_manifest(name))
        print_success("Created agentbox.yaml")

    # Create directories
    for d in ["prompts", "evals", ".agentbox/sessions", ".agentbox/versions"]:
        Path(d).mkdir(parents=True, exist_ok=True)

    # Create eval template
    eval_path = Path("evals/test_suite.yaml")
    if not eval_path.exists():
        eval_path.write_text(generate_eval_template())
        print_success("Created evals/test_suite.yaml")

    # Create .gitignore
    gitignore = Path(".agentbox/.gitignore")
    if not gitignore.exists():
        gitignore.write_text("sessions/\n")
        print_success("Created .agentbox/.gitignore")

    print()
    print_info(f"Edit agentbox.yaml to configure your agent")
    print_info(f"Run {BOLD}agentbox test{RESET} to evaluate")
    print_info(f"Run {BOLD}agentbox tag v0.1.0{RESET} to save a version")
    print()


def cmd_validate(args):
    """Validate the current manifest."""
    from agentbox.manifest import parse_manifest, validate_manifest

    print_header("Validating agent manifest")

    try:
        manifest = parse_manifest(".")
    except (FileNotFoundError, ValueError) as e:
        print_error(str(e))
        return 1

    issues = validate_manifest(manifest)

    print_info(f"Agent: {BOLD}{manifest.name}{RESET} v{manifest.version}")
    print_info(f"Model: {manifest.model}")
    print_info(f"Framework: {manifest.framework}")
    print_info(f"Tools: {len(manifest.tools)}")
    print_info(f"Guardrails: {len(manifest.guardrails)}")
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
    from agentbox.manifest import parse_manifest
    from agentbox.tester import AgentTestRunner

    print_header("Running eval suite")

    try:
        manifest = parse_manifest(".")
    except (FileNotFoundError, ValueError) as e:
        print_error(str(e))
        return 1

    eval_path = manifest.eval_suite or "./evals/test_suite.yaml"
    if not Path(eval_path).exists():
        print_error(f"Eval suite not found: {eval_path}")
        print_info("Run 'agentbox init' to create a default eval suite")
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
    from agentbox.recorder import list_sessions

    print_header("Recorded sessions")

    sessions = list_sessions(".")
    if not sessions:
        print_dim("No sessions recorded yet. Run 'agentbox record' to start.")
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


def cmd_replay(args):
    """Replay a recorded session."""
    from agentbox.recorder import load_session

    if not args:
        print_error("Usage: agentbox replay <session-id>")
        return 1

    print_header(f"Replaying session: {args[0]}")

    try:
        session = load_session(args[0], ".")
    except FileNotFoundError as e:
        print_error(str(e))
        return 1

    print_info(f"Agent: {session['agent_name']} v{session['agent_version']}")
    print_info(f"Model: {session['model']}")
    print_info(f"Status: {session['status']}")
    print_info(f"Duration: {session.get('duration_seconds', 0)}s")
    print_info(f"Cost: ${session['total_cost_usd']:.4f}")
    print()

    for i, action in enumerate(session.get("actions", []), 1):
        atype = action["action_type"]
        icons = {
            "llm_call": f"{BLUE}🤖{RESET}",
            "tool_call": f"{CYAN}🔧{RESET}",
            "decision": f"{GREEN}💡{RESET}",
            "guardrail_triggered": f"{YELLOW}🛡{RESET}",
            "error": f"{RED}❌{RESET}",
        }
        icon = icons.get(atype, "  ")

        print(f"  {DIM}[{i}]{RESET} {icon} {BOLD}{atype}{RESET}", end="")
        if action.get("duration_ms"):
            print(f" {DIM}({action['duration_ms']}ms){RESET}", end="")
        if action.get("cost_usd"):
            print(f" {DIM}(${action['cost_usd']:.4f}){RESET}", end="")
        print()

        content = action.get("content", {})
        for k, v in content.items():
            print(f"      {DIM}{k}: {str(v)[:80]}{RESET}")

    print()
    return 0


def cmd_tag(args):
    """Tag current state as a version."""
    from agentbox.versioner import tag_version

    if not args:
        print_error("Usage: agentbox tag <version>  (e.g., agentbox tag v1.0.0)")
        return 1

    version = args[0]
    print_header(f"Tagging version: {version}")

    try:
        meta = tag_version(version, ".")
        print_success(f"Tagged {version}")
        print_info(f"Hash: {meta['manifest_hash']}")
        print_info(f"Time: {meta['tagged_at']}")
        print()
        print_info(f"Rollback with: {BOLD}agentbox rollback {version}{RESET}")
    except ValueError as e:
        print_error(str(e))
        return 1

    return 0


def cmd_versions(args):
    """List all tagged versions."""
    from agentbox.versioner import list_versions

    print_header("Tagged versions")

    versions = list_versions(".")
    if not versions:
        print_dim("No versions tagged yet. Run 'agentbox tag v0.1.0' to start.")
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
    from agentbox.versioner import rollback_to

    if not args:
        print_error("Usage: agentbox rollback <version>")
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
    from agentbox.scanner import scan_directory, format_scan_results

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
    from agentbox.manifest import parse_manifest

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
    print(f"  {BOLD}Model:{RESET}       {manifest.model}")
    print(f"  {BOLD}Temp:{RESET}        {manifest.temperature}")
    print(f"  {BOLD}Memory:{RESET}      {manifest.memory}")
    print(f"  {BOLD}Tools:{RESET}       {len(manifest.tools)}")
    print(f"  {BOLD}Guardrails:{RESET}  {len(manifest.guardrails)}")
    print(f"  {BOLD}Tags:{RESET}        {', '.join(manifest.tags) if manifest.tags else 'none'}")
    print(f"  {BOLD}Author:{RESET}      {manifest.author or 'not set'}")

    if manifest.system_prompt:
        preview = manifest.system_prompt[:100].replace('\n', ' ')
        print(f"  {BOLD}Prompt:{RESET}      {DIM}{preview}...{RESET}")

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
}


def print_usage():
    print(f"""
{BOLD}{CYAN}⬡ AgentBox{RESET} — Docker for AI Agents
{DIM}Package, test, version, and deploy AI agents.{RESET}

{BOLD}Usage:{RESET}
  agentbox <command> [options]

{BOLD}Commands:{RESET}
  {GREEN}init{RESET} [name]             Create a new agent project
  {GREEN}validate{RESET}                Validate agent manifest
  {GREEN}test{RESET} [--verbose]        Run eval suite
  {GREEN}tag{RESET} <version>           Tag current state (e.g., v1.0.0)
  {GREEN}versions{RESET}               List all tagged versions
  {GREEN}rollback{RESET} <version>      Restore a tagged version
  {GREEN}sessions{RESET}               List recorded sessions
  {GREEN}replay{RESET} <session-id>     Replay a recorded session
  {GREEN}scan{RESET} [directory]        Discover agents in codebase
  {GREEN}info{RESET}                   Show current agent details

{BOLD}Get started:{RESET}
  agentbox init my-agent
  cd my-agent
  agentbox test
  agentbox tag v0.1.0

{DIM}https://agentbox.dev{RESET}
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
