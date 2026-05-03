"""
agentbox.compliance.standards.eu_ai_act
=======================================
Builds the structured document tree for an EU AI Act Annex IV technical
documentation package. The structure mirrors Annex IV's nine sections.
"""

from __future__ import annotations

from agentbox.compliance.generator import ComplianceContext


def build_document(ctx: ComplianceContext) -> dict:
    """Return a serializable dict representing the document structure."""
    m = ctx.manifest
    risk = ctx.risk
    lock = ctx.lock

    sections = []

    # ── 1. General description ────────────────────────────────────
    sections.append({
        "id": "1",
        "heading": "General description",
        "fields": [
            ("System name", m.name),
            ("Version", m.version),
            ("Author / provider", m.author or "Not declared"),
            ("Intended purpose",
             (m.compliance.intended_purpose if m.compliance and m.compliance.intended_purpose
              else "**MISSING — must be filled in.**")),
            ("Affected users",
             m.compliance.affected_users if m.compliance else "internal (default)"),
            ("Out of scope",
             ", ".join(m.compliance.out_of_scope) if (m.compliance and m.compliance.out_of_scope)
             else "Not declared"),
            ("Framework", m.framework),
            ("Foundation model",
             f"{m.effective_provider}/{m.effective_model}"
             + (f" @ {m.model_spec.pinned_version}" if m.model_spec and m.model_spec.pinned_version
                else " (unpinned — risk)")),
        ],
    })

    # ── 2. Detailed system description ────────────────────────────
    tools_text = "\n".join(
        f"- **{t.name}** (`{t.type}`)"
        + (f" → `{t.endpoint}`" if t.endpoint else "")
        + (f" via `{t.module}`" if t.module else "")
        for t in m.tools
    ) or "_No tools declared._"

    sections.append({
        "id": "2",
        "heading": "Detailed system description",
        "subsections": [
            {
                "heading": "2.1 Architecture & methods",
                "body": (
                    f"The agent operates on the {m.effective_provider} platform using model "
                    f"`{m.effective_model}`. It is implemented in the `{m.framework}` framework "
                    f"and exposes the following tools:\n\n{tools_text}"
                ),
            },
            {
                "heading": "2.2 System prompt (excerpt)",
                "body": "```\n" + (m.system_prompt[:2000]
                                    if m.system_prompt else "_No system prompt declared._") + "\n```",
            },
            {
                "heading": "2.3 Foundation model",
                "fields": [
                    ("Provider", m.effective_provider),
                    ("Model", m.effective_model),
                    ("Pinned version",
                     m.model_spec.pinned_version if m.model_spec and m.model_spec.pinned_version
                     else "**NONE — provider may silently update weights**"),
                    ("Temperature", str(m.temperature)),
                    ("Max tokens", str(m.max_tokens)),
                ],
            },
        ],
    })

    # ── 3. Monitoring, functioning, and control ───────────────────
    g = m.guardrail_spec
    monitoring_lines = []
    if g:
        if g.cost.max_usd_per_session is not None:
            monitoring_lines.append(
                f"- **Cost cap:** ${g.cost.max_usd_per_session}/session "
                f"(action: {g.cost.action})"
            )
        if g.iterations.max_llm_calls is not None:
            monitoring_lines.append(
                f"- **Iteration cap:** {g.iterations.max_llm_calls} LLM calls "
                f"(action: {g.iterations.action})"
            )
        if g.tools.allowlist:
            monitoring_lines.append(
                f"- **Tool allowlist:** {', '.join(g.tools.allowlist)} "
                f"(action: {g.tools.action})"
            )
        if g.pii.patterns or g.pii.action != "redact":
            monitoring_lines.append(
                f"- **PII handling:** {g.pii.action} ({g.pii.direction}); "
                f"patterns: {', '.join(g.pii.patterns) or 'all built-in'}"
            )
        if g.rate.max_calls_per_minute is not None:
            monitoring_lines.append(
                f"- **Rate limit:** {g.rate.max_calls_per_minute} calls/minute"
            )
    if not monitoring_lines:
        monitoring_lines.append(
            "_No typed guardrails declared. Article 14 (human oversight) requirements unmet._"
        )

    sections.append({
        "id": "3",
        "heading": "Monitoring, functioning, and control",
        "body": (
            "The system is operated under AgentBox's runtime guard, which intercepts "
            "every LLM and tool call at the API boundary and enforces the following "
            "controls:\n\n" + "\n".join(monitoring_lines)
        ),
    })

    # ── 4. Risk management system ─────────────────────────────────
    rules_text = "\n".join(
        f"- `{f.rule.code}` (→ {f.rule.risk_class}): {f.rule.description}\n"
        f"  - Triggered by: `{f.matched}`"
        for f in risk.fired_rules
    )
    sections.append({
        "id": "4",
        "heading": "Risk management system",
        "subsections": [
            {
                "heading": "4.1 Risk classification",
                "body": (
                    f"**Classified as:** `{risk.risk_class.upper()}`\n\n"
                    f"{risk.summary}\n\n"
                    f"**Rules that fired:**\n{rules_text}\n\n"
                    + (f"**Declared risk in manifest:** `{risk.declared_risk_class}`"
                       if risk.declared_risk_class and risk.declared_risk_class != risk.risk_class
                       else "")
                ),
            },
            {
                "heading": "4.2 Residual risks",
                "body": (
                    "The following residual risks have been identified:\n"
                    "- Provider weight updates not detected by version pinning\n"
                    "- Tool API behavior may change without notice\n"
                    "- Adversarial prompt injection from third-party content\n"
                    "- Statistical drift over deployment lifetime\n\n"
                    "Each is monitored via the agent's session log and seal verification."
                ),
            },
        ],
    })

    # ── 5. Data and data governance ───────────────────────────────
    dh = m.compliance.data_handling if m.compliance else None
    if dh:
        data_fields = [
            ("Processes PII", str(dh.processes_pii)),
            ("PII categories", ", ".join(dh.pii_categories) or "None declared"),
            ("Retention (days)", str(dh.retention_days) if dh.retention_days else "Not declared"),
            ("Data residency", dh.data_residency or "Not declared"),
        ]
    else:
        data_fields = [("Data handling", "**Not declared in manifest.**")]

    sections.append({
        "id": "5",
        "heading": "Data and data governance",
        "fields": data_fields,
    })

    # ── 6. Human oversight ────────────────────────────────────────
    oversight = m.compliance.human_oversight if m.compliance else "none"
    approval_list = (g.tools.require_approval if g and g.tools.require_approval
                     else m.requires_approval)
    sections.append({
        "id": "6",
        "heading": "Human oversight",
        "body": (
            f"Oversight level: **{oversight}**\n\n"
            f"Tools requiring human approval before execution: "
            f"{', '.join(approval_list) if approval_list else '_None declared._'}\n\n"
            "Human operators can interrupt the agent at any time via standard "
            "process management (Ctrl-C in interactive mode, kill signal in production)."
        ),
    })

    # ── 7. Accuracy, robustness, cybersecurity ────────────────────
    ss = ctx.sessions_summary
    sections.append({
        "id": "7",
        "heading": "Accuracy, robustness, cybersecurity",
        "fields": [
            ("Eval suite", m.eval_suite or "Not declared"),
            ("Sessions recorded", str(ss["total"])),
            ("Successful completions", str(ss["completed"])),
            ("Stopped by guardrails", str(ss["guardrail_stopped"])),
            ("Errors", str(ss["errors"])),
            ("Cumulative spend (USD)", f"${ss['total_cost_usd']:.4f}"),
            ("Cybersecurity controls",
             "Tool allowlist enforcement; PII redaction at API boundary; "
             "cost-cap circuit breakers via `agentbox guard`"),
        ],
    })

    # ── 8. Lifecycle changes ──────────────────────────────────────
    if lock:
        seal_fields = [
            ("Last sealed at", lock.sealed_at),
            ("Sealed by", lock.sealed_by),
            ("Seal hash", (lock.seal_hash or "")[:24] + "..." if lock.seal_hash else "Not computed"),
            ("Manifest hash", lock.manifest.get("sha256", "")[:24] + "..." if lock.manifest else ""),
            ("Probe response captured",
             "Yes" if lock.model.get("probe_response_hash") else "No"),
        ]
    else:
        seal_fields = [("Seal status", "**No agent.lock found. Run `agentbox seal`.**")]

    sections.append({
        "id": "8",
        "heading": "Lifecycle changes",
        "fields": seal_fields,
    })

    # ── 9. Compliance with harmonized standards ───────────────────
    sections.append({
        "id": "9",
        "heading": "Compliance with harmonized standards",
        "body": (
            "The provider declares conformity with (mark applicable):\n\n"
            "- [ ] EN ISO/IEC 23894 (AI risk management)\n"
            "- [ ] EN ISO/IEC 42001 (AI management systems)\n"
            "- [ ] EN ISO/IEC TR 24028 (AI trustworthiness)\n"
            "- [ ] CEN/CENELEC harmonized standards (when published)\n\n"
            "Where conformity is claimed, supporting evidence is maintained "
            "alongside this document."
        ),
    })

    return {
        "title": f"Technical Documentation — {m.name} v{m.version}",
        "subtitle": "EU AI Act, Annex IV",
        "generated_at": ctx.generated_at,
        "seal_hash": lock.seal_hash if lock else None,
        "risk_class": risk.risk_class,
        "sections": sections,
    }
